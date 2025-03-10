import os
import tempfile
from flask import Flask, request, jsonify, send_file, Response, stream_with_context
import datetime
from typing import Optional
import logging
from decimal import Decimal
from io import BytesIO
import subprocess
import platform
import time

from db_connector import DatabaseConnector
from report_generator import ReportGenerator
from tax_cal import TaxCalculator  # 导入税额计算器

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("api_service.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 确保single_report文件夹存在
def ensure_dir_exists(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logger.info(f"Created directory: {dir_path}")

# 根据操作系统打开文件
def open_file(filepath):
    if platform.system() == 'Windows':
        os.startfile(filepath)
    elif platform.system() == 'Darwin':  # macOS
        subprocess.call(('open', filepath))
    else:  # linux/unix
        subprocess.call(('xdg-open', filepath))
    logger.info(f"Opened file: {filepath}")

@app.route('/')
def root():
    return {"message": "Transaction Report API is running"}

@app.route('/generate-report/', methods=['POST'])
def generate_report():
    try:
        # 解析请求参数
        request_data = request.json
        if not request_data:
            return jsonify({"error": "Invalid JSON data"}), 400
            
        store_id = request_data.get('store_id')
        date_str = request_data.get('date')
        
        if not store_id or not date_str:
            return jsonify({"error": "Missing required parameters: store_id or date"}), 400
            
        try:
            input_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

        logger.info(f"Generating report for store_id: {store_id}, date: {date_str}")
        
        # 连接数据库
        db = DatabaseConnector()
        
        # 获取商店信息
        store_info = db.get_store_info(store_id)
        if not store_info:
            db.close()
            return jsonify({"error": f"Store with id {store_id} not found"}), 404

        # 查找包含该日期的周账单
        week_bill = db.get_week_bill_by_date(store_id, input_date)
        if not week_bill:
            db.close()
            return jsonify({
                "error": f"No weekly bill found for store {store_id} including date {input_date.strftime('%Y-%m-%d')}"
            }), 404
            
        # 使用周账单的起止日期
        start_date = week_bill["start_date"]
        end_date = week_bill["end_date"]
        logger.info(f"Found weekly bill from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # 查询该周期内的所有订单
        orders = db.get_orders_by_store_and_period(store_id, start_date, end_date)
        logger.info(f"Found {len(orders)} orders in period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

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
        
        # 计算Additional_charge
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
        
        # 构建bill_data
        bill_data = {
            "start_date": start_date,
            "end_date": end_date,
            "store_amount": Decimal(str(week_bill.get("store_amount", 0))),
            "original_price": original_price,
            "discount_fee": Decimal(str(week_bill.get("discount_fee", 0))),
            "refund_amount": Decimal(str(week_bill.get("refund_amount", 0))),
            "product_tax_fee": GST,
            "commission_fee": commission_fee,
            "refund_commission_fee": refund_commission_fee,
            "service_package_fee": service_package_fee,
            "extra_fee": extra_fee,
            "total_orders": total_orders,
            "total_revenue": original_price - Decimal(str(week_bill.get("discount_fee", 0))) - Decimal(str(week_bill.get("refund_amount", 0))),
            "unique_users": len(set(order["user_id"] for order in orders)),
            "GST": GST,
            "GST_total": GST_total,
            "PST_total": PST_total,
            "Additional_charge": additional_charge
        }

        # 其他周账单数据
        for key in ["stripe_fee", "remark"]:
            if key in week_bill:
                if isinstance(week_bill[key], (int, float)):
                    bill_data[key] = Decimal(str(week_bill[key]))
                else:
                    bill_data[key] = week_bill[key]

        # 创建固定目录用于存放生成的报告
        single_report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "single_report")
        ensure_dir_exists(single_report_dir)
        
        # 生成带时间戳的文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"{store_id}_{input_date.strftime('%Y%m%d')}_{timestamp}.pdf"
        report_path = os.path.join(single_report_dir, pdf_filename)
        
        # 生成报告
        report_gen = ReportGenerator(output_dir=os.path.dirname(report_path))
        pdf_path = report_gen.generate_report(bill_data, store_info, orders)
        
        # 重命名文件到带时间戳的名称
        if pdf_path != report_path:
            # 如果生成的文件名与期望的不同，重命名它
            if os.path.exists(report_path):
                os.remove(report_path)  # 如果文件已存在，先删除
            os.rename(pdf_path, report_path)
            logger.info(f"Renamed report file to: {report_path}")
        
        # 自动打开生成的文件
        try:
            open_file(report_path)
        except Exception as e:
            logger.warning(f"Could not automatically open the file: {str(e)}")
            
        db.close()
        
        # 将PDF文件读入内存并返回
        with open(report_path, 'rb') as f:
            pdf_data = f.read()
        
        return send_file(
            BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=pdf_filename
        )

    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        if 'db' in locals():
            db.close()
        return jsonify({"error": f"Failed to generate report: {str(e)}"}), 500

if __name__ == "__main__":
    # 运行服务器，设置host为0.0.0.0以便可以从外部访问
    app.run(host="0.0.0.0", port=5009, debug=True)
