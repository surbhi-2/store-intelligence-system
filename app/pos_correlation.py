# app/pos_correlation.py
"""
Correlate visitor sessions with POS transactions.

Business logic:
A visitor "converted" if they were in the billing zone within 5 minutes
BEFORE a transaction was completed.

This is used to compute:
- Conversion rate
- Which visitors purchased
- Revenue per visitor/session
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Dict, Set, List, Tuple
import structlog

from app.models import EventDB, POSTransactionDB

logger = structlog.get_logger()


class POSCorrelator:
    """
    Correlates visitor events with POS transactions.
    """
    
    CORRELATION_WINDOW_MINUTES = 5  # Visitor in billing within 5 min before transaction
    
    def __init__(self, db: Session, store_id: str, start_time: datetime, end_time: datetime):
        """
        Initialize correlator for a time window.
        
        Args:
            db: SQLAlchemy session
            store_id: Which store to correlate
            start_time: Start of time window (inclusive)
            end_time: End of time window (inclusive)
        """
        self.db = db
        self.store_id = store_id
        self.start_time = start_time
        self.end_time = end_time
        
        # Load all data for this window
        self._load_data()
    
    def _load_data(self):
        """Load all events and transactions for the time window."""
        
        # Get all events in window (excluding staff)
        self.all_events = self.db.query(EventDB).filter(
            and_(
                EventDB.store_id == self.store_id,
                EventDB.timestamp >= self.start_time,
                EventDB.timestamp <= self.end_time,
                EventDB.is_staff == False
            )
        ).all()
        
        # Get all transactions in window
        self.all_transactions = self.db.query(POSTransactionDB).filter(
            and_(
                POSTransactionDB.store_id == self.store_id,
                POSTransactionDB.timestamp >= self.start_time,
                POSTransactionDB.timestamp <= self.end_time
            )
        ).all()
        
        # Filter: only billing zone events
        self.billing_events = [e for e in self.all_events if e.zone_id == "BILLING"]
        
        logger.info(
            "pos_correlation_data_loaded",
            store_id=self.store_id,
            total_events=len(self.all_events),
            billing_events=len(self.billing_events),
            transactions=len(self.all_transactions)
        )
    
    def get_converted_visitors(self) -> Set[str]:
        """
        Find all visitor_ids who converted (visited billing zone + transaction).
        
        Returns:
            Set of visitor_ids that converted
        """
        converted = set()
        
        for transaction in self.all_transactions:
            # Find any visitor in billing zone within 5 min before this transaction
            for event in self.billing_events:
                time_diff = (transaction.timestamp - event.timestamp).total_seconds() / 60
                
                print(
                    "EVENT:",
                    event.timestamp,
                    "TXN:",
                    transaction.timestamp,
                    "DIFF:",
                    round(time_diff, 2)
                )
                # Visitor must be in billing zone 0-5 minutes before transaction
                if 0 <= time_diff <= self.CORRELATION_WINDOW_MINUTES:
                    converted.add(event.visitor_id)
                    logger.debug(
                        "visitor_converted",
                        visitor_id=event.visitor_id,
                        transaction_id=transaction.transaction_id,
                        time_diff_minutes=round(time_diff, 2)
                    )
                    break  # Count this visitor once per transaction
        
        return converted
      
    
    
    def get_revenue_per_visitor(self) -> Dict[str, float]:
        """
        Calculate total revenue attributed to each visitor.
        
        Multiple transactions in the 5-min window count toward same visitor.
        
        Returns:
            Dict: {visitor_id: total_revenue_inr}
        """
        revenue_map = {}
        
        for transaction in self.all_transactions:
            # Find visitors in billing zone within 5 min before this transaction
            for event in self.billing_events:
                time_diff = (transaction.timestamp - event.timestamp).total_seconds() / 60
                
                if 0 <= time_diff <= self.CORRELATION_WINDOW_MINUTES:
                    visitor_id = event.visitor_id
                    
                    # Add this transaction value to the visitor's total
                    if visitor_id not in revenue_map:
                        revenue_map[visitor_id] = 0.0
                    
                    revenue_map[visitor_id] += transaction.basket_value
                    break
        
        return revenue_map
    
    
    def get_total_revenue(self) -> float:
        """Get total revenue from all converted transactions."""
        return sum(t.basket_value for t in self.all_transactions)
    
    def get_conversion_rate(self) -> float:
        """
        Calculate conversion rate: (converted visitors / total unique visitors) * 100
        
        Returns:
            float: Percentage (0-100)
        """
        # Total unique visitors (ENTRY events)
        entry_events = [e for e in self.all_events if e.event_type == "ENTRY"]
        unique_visitors = len(set(e.visitor_id for e in entry_events))
        
        if unique_visitors == 0:
            return 0.0
        
        # Converted visitors
        converted = self.get_converted_visitors()
        
        rate = (len(converted) / unique_visitors) * 100
        return round(rate, 2)
    
    def get_avg_revenue_per_visitor(self) -> float:
        """
        Average basket value for converting visitors.
        
        Returns:
            float: Average in INR
        """
        revenue_map = self.get_revenue_per_visitor()
        
        if not revenue_map:
            return 0.0
        
        avg = sum(revenue_map.values()) / len(revenue_map)
        return round(avg, 2)
    
    def get_abandoned_visitors(self) -> Set[str]:
        """
        Visitors who reached billing zone but didn't complete a transaction.
        
        Returns:
            Set of visitor_ids that abandoned
        """
        # All visitors who entered billing zone
        all_billing_visitors = set(e.visitor_id for e in self.billing_events)
        
        # Visitors who converted
        converted = self.get_converted_visitors()
        
        # Abandoned = visited billing but didn't convert
        abandoned = all_billing_visitors - converted
        
        return abandoned
    
    def get_abandonment_rate(self) -> float:
        """
        Abandonment rate: (abandoned / total_billing_zone_visitors) * 100
        
        Returns:
            float: Percentage (0-100)
        """
        all_billing_visitors = set(e.visitor_id for e in self.billing_events)
        
        if len(all_billing_visitors) == 0:
            return 0.0
        
        abandoned = self.get_abandoned_visitors()
        rate = (len(abandoned) / len(all_billing_visitors)) * 100
        
        return round(rate, 2)
    
    def get_summary(self) -> Dict:
        """Get all correlation metrics in one dict."""
        return {
            "store_id": self.store_id,
            "converted_visitors": len(self.get_converted_visitors()),
            "abandoned_visitors": len(self.get_abandoned_visitors()),
            "total_transactions": len(self.all_transactions),
            "total_revenue": self.get_total_revenue(),
            "conversion_rate": self.get_conversion_rate(),
            "abandonment_rate": self.get_abandonment_rate(),
            "avg_revenue_per_visitor": self.get_avg_revenue_per_visitor(),
            "revenue_per_visitor": self.get_revenue_per_visitor()
        }