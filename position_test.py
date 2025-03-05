import os
import datetime
import json
from report_generator import ReportGenerator
from PIL import Image, ImageDraw, ImageFont

def main():
    # 使用测试参数生成测试 PDF
    # 设置临时输出目录
    test_output_dir = os.path.join(os.path.dirname(__file__), "generated_reports", "test_batch")
    if not os.path.exists(test_output_dir):
        os.makedirs(test_output_dir)
    
    # 初始化 ReportGenerator
    report_gen = ReportGenerator(output_dir=test_output_dir)
    
    # 构造测试数据
    bill_data = {
        'start_date': datetime.datetime(2023, 1, 1),
        'end_date': datetime.datetime(2023, 1, 31),
        'settlement_amount': 1234.56,
        'total_orders': 10,      # 将在 ReportGenerator 中覆盖
        'total_revenue': 7890.12 # 将在 ReportGenerator 中覆盖
    }
    
    store_info = {
        'id': 1,
        'name': 'Test Store',
        'address': '123 Test St.'
    }
    
    # 构造10个测试订单
    orders = []
    for i in range(10):
        orders.append({
            'created_at': datetime.datetime(2023, 1, 5 + i),
            'pickup_code': f"PC{i+1:03}",
            'store_total_fee': 100.0 + i * 10,
            'user_id': i + 1,  # 添加 user_id 字段，确保有对应的用户数据
            'pay_type': [5, 7, 6][i % 3]  # 新增 pay_type 字段
        })
    
    # 生成测试 PDF
    pdf_path = report_gen.generate_report(bill_data, store_info, orders)
    print(f"测试 PDF 已生成：{pdf_path}")
    
    # 如有需要，可将当前测试参数写入 pos_config.json 以便保存调整后的位置（需手动修改后再次保存）
    config_path = os.path.join(os.path.dirname(__file__), "pos_config.json")
    with open(config_path, "r") as f:
        config = json.load(f)
    print("当前位置参数：")
    print(json.dumps(config, indent=4))

if __name__ == "__main__":
    main()
