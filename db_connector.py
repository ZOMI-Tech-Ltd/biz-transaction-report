import mysql.connector
import os
from dotenv import load_dotenv
from decimal import Decimal

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
        """Get all bills with store_amount != 0"""
        query = """
            SELECT * FROM order_bill_week
            WHERE store_amount != 0
        """
        # 只选取未结算的非0账单
        self.cursor.execute(query)
        return self.cursor.fetchall()
    
    def get_store_info(self, store_id):
        """Get store information by store_id"""
        query = """
            SELECT * FROM store
            WHERE id = %s AND deleted_at IS NULL
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
        """Get orders for a specific store within a time period (inclusive of end_date)"""
        query = """
            SELECT * FROM `order`
            WHERE store_id = %s 
              AND created_at >= %s 
              AND created_at < DATE_ADD(%s, INTERVAL 1 DAY)
              AND state = 5000
              AND payment_method != 4
            ORDER BY created_at
        """
        self.cursor.execute(query, (store_id, start_date, end_date))
        return self.cursor.fetchall()
    
    def get_week_bill_by_date(self, store_id, date):
        """根据日期找到包含该日期的周账单，并转换金额为Decimal"""
        query = """
            SELECT * FROM order_bill_week
            WHERE store_id = %s 
              AND start_date <= %s 
              AND end_date >= %s
        """
        self.cursor.execute(query, (store_id, date, date))
        result = self.cursor.fetchone()
        
        # 如果结果存在，将所有金额字段转换为Decimal
        if result:
            money_fields = [
                'store_amount', 'original_price', 'discount_fee', 'refund_amount',
                'product_tax_fee', 'commission_fee', 'refund_commission_fee',
                'service_package_fee', 'extra_fee', 'stripe_fee'
            ]
            for field in money_fields:
                if field in result and result[field] is not None:
                    result[field] = Decimal(str(result[field]))
        
        return result
    
    def get_store_contact_email(self, store_id):
        """从store_contact表获取商店联系人邮箱"""
        query = """
            SELECT contact_email FROM store_contact WHERE deleted_at IS NULL AND store_id = %s
        """
        self.cursor.execute(query, (store_id,))
        result = self.cursor.fetchone()
        return result['contact_email'] if result else None
        
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.connection.close()