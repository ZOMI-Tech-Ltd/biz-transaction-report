import os
import sys
from db_connector import DatabaseConnector
from report_generator import ReportGenerator
import logging
import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("report_generation.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def main():
    # 如果传入两个参数，则单报告模式：store_id 和日期（格式：YYYY-MM-DD）
    if len(sys.argv) == 3:
        try:
            store_id = int(sys.argv[1])
            report_date = datetime.datetime.strptime(sys.argv[2], "%Y-%m-%d")
        except Exception as e:
            logger.error("Invalid arguments. Usage: python main.py <store_id> <YYYY-MM-DD>")
            return

        db = DatabaseConnector()
        store_info = db.get_store_info(store_id)
        if not store_info:
            logger.error(f"Store with id {store_id} not found.")
            db.close()
            return

        # 查询该日期内的订单（按天统计，即 [report_date, report_date]）
        orders = db.get_orders_by_store_and_period(store_id, report_date, report_date)
        logger.info(f"Found {len(orders)} orders for store_id {store_id} on {report_date.strftime('%Y-%m-%d')}")

        # 填充每个订单的 user_name
        for order in orders:
            order["user_name"] = db.get_user_profile(order["user_id"])
        
        total_orders = len(orders)
        original_price = sum(order["store_total_fee"] for order in orders) if orders else 0
        bill_data = {
            "start_date": report_date,
            "end_date": report_date,
            "store_amount": original_price,
            "original_price": original_price,
            "discount_fee": 0,
            "refund_amount": 0,
            "product_tax_fee": 0,
            "commission_fee": 0,
            "refund_commission_fee": 0,
            "service_package_fee": 0,
            "total_orders": total_orders,
            "total_revenue": original_price,
            "unique_users": len(set(order["user_id"] for order in orders))
        }

        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "generated_reports",
                                  f"report_single_{store_id}_{report_date.strftime('%Y%m%d')}")
        report_gen = ReportGenerator(output_dir=output_dir)
        pdf_path = report_gen.generate_report(bill_data, store_info, orders)
        logger.info(f"Report for store {store_id} on {report_date.strftime('%Y-%m-%d')} generated: {pdf_path}")
        db.close()
    else:
        # 批量处理逻辑（原有代码）...
        logger.info("Starting batch report generation process")

        try:
            # Create timestamped batch folder for this run
            batch_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Use a better way to get the base directory
            base_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "generated_reports"
            )

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
                store_info = db.get_store_info(bill["store_id"])
                if not store_info:
                    logger.warning(f"Store info not found for store_id: {bill['store_id']}")
                    continue

                # Get orders for this store within the specified period
                orders = db.get_orders_by_store_and_period(
                    bill["store_id"], bill["start_date"], bill["end_date"]
                )
                logger.info(f"Found {len(orders)} orders for {store_info['name']}")

                # 填充每个订单的 user_name，从 user_profile 表获取
                for order in orders:
                    order["user_name"] = db.get_user_profile(order["user_id"])

                # Add total_orders based on orders count
                bill["total_orders"] = len(orders)
                # Calculate total_revenue = original_price - refund_amount
                bill["total_revenue"] = (
                    bill.get("original_price", 0)
                    - bill.get("discount_fee", 0)
                    - bill.get("refund_amount", 0)
                )
                # 计算unique_users
                bill["unique_users"] = len(set(order["user_id"] for order in orders))

                # 新增 GST from product_tax_fee
                bill["GST"] = bill.get("product_tax_fee", 0)

                # 新增 Additional_charge = (commission_fee - refund_commission_fee) + service_package_fee
                
                bill["Additional_charge"] = (
                    bill.get("commission_fee", 0)
                    - bill.get("refund_commission_fee", 0)
                    + bill.get("service_package_fee", 0)
                )

                # Generate report
                report_path = report_gen.generate_report(bill, store_info, orders)
                successful_reports.append(
                    {
                        "store_name": store_info["name"],
                        "store_id": bill["store_id"],
                        "report_path": report_path,
                    }
                )
                logger.info(f"Generated report: {report_path}")

            # Create a summary file with links to all generated reports
            summary_path = os.path.join(batch_dir, "summary.txt")
            with open(summary_path, "w") as f:
                f.write(f"Report Generation Summary - {batch_timestamp}\n")
                f.write(f"Total reports generated: {len(successful_reports)}\n\n")

                for idx, report in enumerate(successful_reports, 1):
                    f.write(f"{idx}. {report['store_name']} (ID: {report['store_id']})\n")
                    f.write(f"   Path: {report['report_path']}\n\n")

            logger.info(
                f"Report generation completed successfully. Summary saved to: {summary_path}"
            )
            logger.info(f"All reports saved in: {batch_dir}")

        except Exception as e:
            logger.error(f"Error generating reports: {e}", exc_info=True)

        finally:
            # Close database connection
            if "db" in locals():
                db.close()


if __name__ == "__main__":
    main()
