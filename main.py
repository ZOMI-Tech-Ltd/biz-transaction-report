import os
import sys
from db_connector import DatabaseConnector
from report_generator import ReportGenerator
from tax_cal import TaxCalculator  # 导入税额计算器
import logging
import datetime
from decimal import Decimal

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
            input_date = datetime.datetime.strptime(sys.argv[2], "%Y-%m-%d")
        except Exception as e:
            logger.error("Invalid arguments. Usage: python main.py <store_id> <YYYY-MM-DD>")
            return

        db = DatabaseConnector()
        store_info = db.get_store_info(store_id)
        if not store_info:
            logger.error(f"Store with id {store_id} not found.")
            db.close()
            return

        # 查找包含该日期的周账单
        week_bill = db.get_week_bill_by_date(store_id, input_date)
        if not week_bill:
            logger.error(f"No weekly bill found for store {store_id} including date {input_date.strftime('%Y-%m-%d')}.")
            db.close()
            return
            
        # 使用周账单的起止日期
        start_date = week_bill["start_date"]
        end_date = week_bill["end_date"]
        logger.info(f"Found weekly bill from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} for store_id {store_id}")
        
        # 查询该周期内的所有订单
        orders = db.get_orders_by_store_and_period(store_id, start_date, end_date)
        logger.info(f"Found {len(orders)} orders for store_id {store_id} in period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        # 填充每个订单的 user_name
        for order in orders:
            order["user_name"] = db.get_user_profile(order["user_id"])
        
        # 计算所有订单的PST总额
        order_ids = [order.get("id") for order in orders if order.get("id")]
        tax_calculator = TaxCalculator()
        tax_totals = tax_calculator.calculate_taxes(order_ids)
        tax_calculator.close()
        
        # 从周账单中获取数据，使用Decimal确保精度
        total_orders = len(orders)
        
        # 确保所有金额使用Decimal
        original_price = Decimal(str(week_bill.get("original_price", 0)))
        GST = Decimal(str(week_bill.get("product_tax_fee", 0)))
        PST_total = Decimal(str(tax_totals["PST_total"]))
        GST_total = GST - PST_total  # 使用Decimal计算
        
        # 计算Additional_charge，使用与批量报告相同的公式
        commission_fee = Decimal(str(week_bill.get("commission_fee", 0)))
        refund_commission_fee = Decimal(str(week_bill.get("refund_commission_fee", 0)))
        service_package_fee = Decimal(str(week_bill.get("service_package_fee", 0)))
        extra_fee = Decimal(str(week_bill.get("extra_fee", 0)))
        
        additional_charge = -(
            commission_fee
            - refund_commission_fee
            + service_package_fee
            - extra_fee
        )
        
        # 构建bill_data时确保所有金额值都是Decimal
        bill_data = {
            "start_date": start_date,
            "end_date": end_date,
            "store_amount": Decimal(str(week_bill.get("store_amount", 0))),
            "original_price": original_price,
            "discount_fee": Decimal(str(week_bill.get("discount_fee", 0))),
            "refund_amount": Decimal(str(week_bill.get("refund_amount", 0))),
            "pickup_tip_fee": Decimal(str(week_bill.get("pickup_tip_fee", 0))),
            "product_tax_fee": GST,  # 这是原始 GST
            "commission_fee": commission_fee,
            "refund_commission_fee": refund_commission_fee,
            "service_package_fee": service_package_fee,
            "extra_fee": extra_fee,
            "total_orders": total_orders,
            "total_revenue": original_price - Decimal(str(week_bill.get("discount_fee", 0))) - Decimal(str(week_bill.get("refund_amount", 0))),
            "unique_users": len(set(order["user_id"] for order in orders)),
            "GST": GST,  # 设置从周账单中获取的 GST
            "GST_total": GST_total,  # 设置为 GST - PST_total
            "PST_total": PST_total,    # 从订单计算的 PST_total
            "Additional_charge": additional_charge  # 添加 Additional_charge
        }

        # 其他周账单数据，使用Decimal转换数值
        for key in ["stripe_fee", "remark"]:
            if key in week_bill:
                if isinstance(week_bill[key], (int, float)):
                    bill_data[key] = Decimal(str(week_bill[key]))
                else:
                    bill_data[key] = week_bill[key]

        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "generated_reports",
                                  f"report_single_{store_id}_{input_date.strftime('%Y%m%d')}")
        report_gen = ReportGenerator(output_dir=output_dir)
        pdf_path = report_gen.generate_report(bill_data, store_info, orders)
        logger.info(f"Report for store {store_id} on {input_date.strftime('%Y-%m-%d')} generated: {pdf_path}")
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
            tax_calculator = TaxCalculator() # 实例化税额计算器

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

                # 计算所有订单的PST总额，确保使用Decimal
                order_ids = [order.get("id") for order in orders if order.get("id")]
                tax_totals = tax_calculator.calculate_taxes(order_ids)
                
                # 设置 GST 和计算 GST_total，确保使用Decimal
                GST = Decimal(str(bill.get("product_tax_fee", 0)))
                PST_total = Decimal(str(tax_totals["PST_total"]))
                bill["GST"] = GST
                bill["GST_total"] = GST - PST_total  # 使用Decimal计算
                bill["PST_total"] = PST_total

                # Add total_orders based on orders count
                bill["total_orders"] = len(orders)
                # Calculate total_revenue = original_price - refund_amount
                bill["total_revenue"] = (
                    Decimal(str(bill.get("original_price", 0)))
                    - Decimal(str(bill.get("discount_fee", 0)))
                    - Decimal(str(bill.get("refund_amount", 0)))
                )
                # 计算unique_users
                bill["unique_users"] = len(set(order["user_id"] for order in orders))

                # 新增 GST from product_tax_fee
                bill["GST"] = bill.get("product_tax_fee", 0)

                # 确保Additional_charge计算使用Decimal
                bill["Additional_charge"] = -(
                    Decimal(str(bill.get("commission_fee", 0)))
                    - Decimal(str(bill.get("refund_commission_fee", 0)))
                    + Decimal(str(bill.get("service_package_fee", 0)))
                    - Decimal(str(bill.get("extra_fee", 0)))
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

            tax_calculator.close() # 关闭税额计算器连接

        except Exception as e:
            logger.error(f"Error generating reports: {e}", exc_info=True)

        finally:
            # Close database connection
            if "db" in locals():
                db.close()


if __name__ == "__main__":
    main()