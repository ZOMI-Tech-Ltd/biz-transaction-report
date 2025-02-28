import os
from db_connector import DatabaseConnector
from report_generator import ReportGenerator
import logging
import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("report_generation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting report generation process")
    
    try:
        # Create timestamped batch folder for this run
        batch_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use a better way to get the base directory
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_reports")
        
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        
        batch_dir = os.path.join(base_dir, f"report_batch_{batch_timestamp}")
        
        # Connect to database
        db = DatabaseConnector()
        report_gen = ReportGenerator(output_dir=batch_dir)
        
        # Get all pending bills
        bills = db.get_pending_bills()
        logger.info(f"Found {len(bills)} bills to process")
        
        successful_reports = []
        
        for bill in bills:
            logger.info(f"Processing bill for store_id: {bill['store_id']}")
            
            # Get store information
            store_info = db.get_store_info(bill['store_id'])
            if not store_info:
                logger.warning(f"Store info not found for store_id: {bill['store_id']}")
                continue
            
            # Get orders for this store within the specified period
            orders = db.get_orders_by_store_and_period(
                bill['store_id'], 
                bill['start_date'], 
                bill['end_date']
            )
            logger.info(f"Found {len(orders)} orders for {store_info['name']}")
            
            # Add total_orders and total_revenue to bill data for the overview page
            bill['total_orders'] = len(orders)
            bill['total_revenue'] = sum(order['store_total_fee'] for order in orders)
            
            # Generate report
            report_path = report_gen.generate_report(bill, store_info, orders)
            successful_reports.append({
                'store_name': store_info['name'],
                'store_id': bill['store_id'],
                'report_path': report_path
            })
            logger.info(f"Generated report: {report_path}")
        
        # Create a summary file with links to all generated reports
        summary_path = os.path.join(batch_dir, "summary.txt")
        with open(summary_path, 'w') as f:
            f.write(f"Report Generation Summary - {batch_timestamp}\n")
            f.write(f"Total reports generated: {len(successful_reports)}\n\n")
            
            for idx, report in enumerate(successful_reports, 1):
                f.write(f"{idx}. {report['store_name']} (ID: {report['store_id']})\n")
                f.write(f"   Path: {report['report_path']}\n\n")
        
        logger.info(f"Report generation completed successfully. Summary saved to: {summary_path}")
        logger.info(f"All reports saved in: {batch_dir}")
    
    except Exception as e:
        logger.error(f"Error generating reports: {e}", exc_info=True)
    
    finally:
        # Close database connection
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
