import os
import datetime
import math
from decimal import Decimal
from report_generator import ReportGenerator

def generate_manual_report(store_data, bill_data, orders_data, generate_additional_page=True, output_dir=None):
    """
    生成手动报告，不需要数据库连接
    
    参数:
    - store_data: 包含商店信息的字典 (name, id, address)
    - bill_data: 包含账单信息的字典
    - orders_data: 包含订单信息的字典列表
    - generate_additional_page: 是否生成额外费用页面
    - output_dir: 可选的输出目录
    
    返回:
    - 生成的PDF文件路径
    """
    # 创建报告生成器
    report_gen = ReportGenerator(output_dir=output_dir)
    
    # 确保所有金额都转换为 Decimal
    for key in bill_data:
        if isinstance(bill_data[key], (int, float)) and key not in ['id', 'store_id', 'total_orders', 'unique_users']:
            bill_data[key] = Decimal(str(bill_data[key]))
    
    # 生成报告
    pdf_path = report_gen.generate_report(bill_data, store_data, orders_data)
    
    return pdf_path


def main():
    """手动报告生成器示例用法"""
    
    # --- 商店信息 ---
    store_data = {
        "id": 123,  # 商店ID（必须）
        "name": "示例商店名称",  # 商店名称
        "address": "某市某区某街123号"  # 商店地址
    }
    
    # --- 账单信息 ---
    start_date = datetime.datetime.strptime("2023-01-01", "%Y-%m-%d")
    end_date = datetime.datetime.strptime("2023-01-07", "%Y-%m-%d")
    
    bill_data = {
        # 日期
        "start_date": start_date,  # 开始日期
        "end_date": end_date,      # 结束日期
        
        # 金额字段（会自动转换为Decimal）
        "store_amount": 1000.00,   # 商店总额
        "original_price": 1200.00, # 原始价格（未折扣前）
        "discount_fee": 50.00,     # 折扣金额
        "refund_amount": 150.00,   # 退款金额
        "product_tax_fee": 80.00,  # 产品税费（GST）
        "commission_fee": 60.00,   # 佣金
        "refund_commission_fee": 10.00,  # 退款佣金
        "asset_balance_repayment": 20.00,    # 服务包费用
        "extra_fee": 5.00,         # 额外费用
        "stripe_fee": 30.00,       # Stripe处理费
        "pickup_tip_fee": 0.00,    # 取货小费
        "remark": "特殊促销",      # 额外费用备注
        
        # 计算字段（可以手动设置）
        "total_orders": 10,        # 总订单数
        "total_revenue": 1000.00,  # 总收入
        "unique_users": 8,         # 唯一用户数
        "GST": 80.00,              # GST（与product_tax_fee相同）
        "GST_total": 60.00,        # GST总额
        "PST_total": 20.00,        # PST总额
        "Additional_charge": -65.00  # 额外费用
    }
    
    # --- 订单数据 ---
    # 每个订单代表详细页面中的一行
    orders_data = [
        {
            "id": 1001,
            "store_id": 123,
            "user_id": 5001,
            "user_name": "张三",  # 显示的用户名
            "created_at": datetime.datetime.strptime("2023-01-01", "%Y-%m-%d"),
            "pickup_code": "A123",  # 取货码
            "store_total_fee": 120.50,  # 商店总费用
            "tip_fee": 5.00,  # 小费
            "refund_amount": 0.00,  # 退款金额
            "payment_method": 7,  # 5: Apple Pay, 6: Google Pay, 7: Card
            "state": 5000,  # 5000: 已完成
            "channel": 2,  # 2: 自取（影响小费计算）
        },
        {
            "id": 1002,
            "store_id": 123,
            "user_id": 5002,
            "user_name": "李四",
            "created_at": datetime.datetime.strptime("2023-01-02", "%Y-%m-%d"),
            "pickup_code": "B456",
            "store_total_fee": 85.75,
            "tip_fee": 0.00,
            "refund_amount": 10.00,
            "payment_method": 5,  # Apple Pay
            "state": 5000,  # 已完成
            "channel": 1,  # 非自取
        },
        # 可以根据需要添加更多订单（每页最多23个）
    ]
    
    # --- 额外费用项目 ---
    # 决定是否生成额外费用页面取决于bill_data中的相关费用是否非零：
    # commission_fee, refund_commission_fee, asset_balance_repayment, extra_fee
    # 如果想要控制是否生成额外费用页面，需要相应地设置上述字段
    
    # 生成报告
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_reports")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    pdf_path = generate_manual_report(
        store_data, 
        bill_data, 
        orders_data,
        generate_additional_page=True,  # 如果不需要额外页面，设为False并确保相关费用为0
        output_dir=output_dir
    )
    
    print(f"报告生成成功: {pdf_path}")


if __name__ == "__main__":
    main()
