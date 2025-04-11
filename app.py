import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
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
import base64
import mailchimp_transactional as MailchimpTransactional
from mailchimp_transactional.api_client import ApiClientError

from db_connector import DatabaseConnector
from report_generator import ReportGenerator
from tax_cal import TaxCalculator  # 导入税额计算器

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("api_service.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Mandrill API相关常量
MANDRILL_API_KEY = os.environ.get("MANDRILL_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "hello@zomi.menu")
FROM_NAME = os.environ.get("FROM_NAME", "ZOMI Team")

AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
S3_BUCKET = os.environ.get("AWS_BUCKET_NAME", "zomi-transaction-reports")

app = Flask(__name__)


# 添加上传函数
def upload_to_s3(file_path, file_name=None):
    """
    将文件上传到 S3 并返回可访问的 URL
    """
    if not file_name:
        file_name = os.path.basename(file_path)
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION
        )
        
        # 上传文件到 S3
        s3_client.upload_file(
            file_path,
            S3_BUCKET,
            file_name,
            ExtraArgs={
                'ContentType': 'application/pdf',
                'ACL': 'public-read'  # 设置为公开可读
            }
        )
        
        # 构建并返回 URL
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{file_name}"
        logger.info(f"File uploaded to S3: {url}")
        return url
    
    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        raise

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
        asset_balance_repayment = Decimal(str(week_bill.get("asset_balance_repayment", 0)))
        extra_fee = Decimal(str(week_bill.get("extra_fee", 0)))
        
        # 计算Additional_charge, 为负数
        additional_charge = -(
            commission_fee
            - refund_commission_fee
            + asset_balance_repayment
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
            "pickup_tip_fee": Decimal(str(week_bill.get("pickup_tip_fee", 0))),
            "product_tax_fee": GST,
            "commission_fee": commission_fee,
            "refund_commission_fee": refund_commission_fee,
            "asset_balance_repayment": asset_balance_repayment,
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
        # try:
        #     open_file(report_path)
        # except Exception as e:
        #     logger.warning(f"Could not automatically open the file: {str(e)}")
            
        db.close()
        
        try:
            s3_url = upload_to_s3(report_path, pdf_filename)
            # 按照要求的格式返回 URL
            return jsonify({
                "code": 0,
                "data": {
                    "url": s3_url
                }
            })
        except Exception as s3_error:
            logger.error(f"Error uploading to S3: {str(s3_error)}", exc_info=True)
            # 如果 S3 上传失败，返回错误信息
            return jsonify({
                "code": 1,
                "msg": f"Failed to upload report to S3: {str(s3_error)}"
            }), 500

    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        if 'db' in locals():
            db.close()
        return jsonify({
            "code": 1,
            "msg": f"Failed to generate report: {str(e)}"
        }), 500


@app.route('/generate-and-email-report/', methods=['POST'])
def generate_and_email_report():
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

        logger.info(f"Generating report and sending email for store_id: {store_id}, date: {date_str}")
        
        # 连接数据库
        db = DatabaseConnector()
        
        # 获取商店信息
        store_info = db.get_store_info(store_id)
        if not store_info:
            db.close()
            return jsonify({"error": f"Store with id {store_id} not found"}), 404

        # 获取商店联系人邮箱
        contact_email = db.get_store_contact_email(store_id)
        if not contact_email:
            db.close()
            return jsonify({"error": f"No contact email found for store {store_id}"}), 404
        
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
        asset_balance_repayment = Decimal(str(week_bill.get("asset_balance_repayment", 0)))
        extra_fee = Decimal(str(week_bill.get("extra_fee", 0)))
        
        # 计算Additional_charge, 为负数
        additional_charge = -(
            commission_fee
            - refund_commission_fee
            + asset_balance_repayment
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
            "pickup_tip_fee": Decimal(str(week_bill.get("pickup_tip_fee", 0))),
            "commission_fee": commission_fee,
            "refund_commission_fee": refund_commission_fee,
            "asset_balance_repayment": asset_balance_repayment,
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
        
        # 读取PDF文件并编码为base64
        with open(report_path, 'rb') as f:
            pdf_data = f.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        

        client = MailchimpTransactional.Client(MANDRILL_API_KEY)
        # 使用Mandrill API发送电子邮件
        store_name = store_info.get("name", f"Store #{store_id}")
        if not MANDRILL_API_KEY:
            logger.error("MANDRILL_API_KEY not set")
            return jsonify({"error": "MANDRILL_API_KEY not configured"}), 500

    
        message = {
            "from_email": FROM_EMAIL,
            "from_name": FROM_NAME,
            "subject": "Weekly Payout Report | ZOMI",
            "to": [{"email": contact_email, "type": "to"}],
            "global_merge_vars": [
                {"name": "COMPANY", "content": store_name},
                {"name": "Startdate", "content": start_date.strftime("%Y/%m/%d")},
                {"name": "Enddate", "content": end_date.strftime("%Y/%m/%d")},
            ],
            # 添加报告作为附件
            "attachments": [
                {
                    "type": "application/pdf",
                    "name": pdf_filename,
                    "content": pdf_base64,
                }
            ],
        }

        try:
            response = client.messages.send_template(
                {
                    "template_name": "transaction-report",  # Mandrill模板名称
                    "template_content": [],
                    "message": message,
                }
            )
            logger.info(f"Mandrill send response: {response}")
            db.close()
            
            return (
                jsonify(
                    {
                        "message": "Report generated and email sent successfully.",
                        "mandrill_response": response,
                        "report_path": report_path,
                    }
                ),
                200,
            )
        except ApiClientError as e:
            logger.error(f"Mandrill API error: {e.text}")
            db.close()
            return jsonify({"error": f"Failed to send email: {e.text}"}), 500

    except Exception as e:
        logger.error(f"Error generating report or sending email: {str(e)}", exc_info=True)
        if 'db' in locals():
            db.close()
        return jsonify({"error": f"Failed to generate report or send email: {str(e)}"}), 500

if __name__ == "__main__":
    # 运行服务器，设置host为0.0.0.0以便可以从外部访问
    app.run(host="0.0.0.0", port=5009, debug=False)

