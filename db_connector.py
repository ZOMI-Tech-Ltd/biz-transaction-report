import mysql.connector
import os
from dotenv import load_dotenv

class DatabaseConnector:
    def __init__(self):
        load_dotenv()
        self.connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASS'),
            database=os.getenv('MYSQL_DB')
        )
        self.cursor = self.connection.cursor(dictionary=True)
    
    def get_pending_bills(self):
        """Get all bills with settlement_amount != 0"""
        query = """
            SELECT * FROM order_bill_week
            WHERE settlement_amount != 0
        """
        self.cursor.execute(query)
        return self.cursor.fetchall()
    
    def get_store_info(self, store_id):
        """Get store information by store_id"""
        query = """
            SELECT * FROM store
            WHERE id = %s
        """
        self.cursor.execute(query, (store_id,))
        return self.cursor.fetchone()
    
    def get_user_profile(self, user_id):
        """Get user profile information by user_id"""
        query = """
            SELECT name FROM user_profile
            WHERE user_id = %s
        """
        self.cursor.execute(query, (user_id,))
        result = self.cursor.fetchone()
        return result['name'] if result else ""
    
    def get_orders_by_store_and_period(self, store_id, start_date, end_date):
        """Get orders for a specific store within a time period"""
        query = """
            SELECT * FROM `order`
            WHERE store_id = %s AND created_at BETWEEN %s AND %s
            ORDER BY created_at
        """
        self.cursor.execute(query, (store_id, start_date, end_date))
        return self.cursor.fetchall()
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.connection.close()
