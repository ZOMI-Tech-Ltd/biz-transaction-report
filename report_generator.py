import os
import json
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import PyPDF2
import io
import math
import datetime
from decimal import Decimal  # 新增导入


class ReportGenerator:
    def __init__(self, output_dir=None):
        # Create a timestamp-based reports folder if none specified
        if output_dir is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = os.path.abspath(
        os.path.join("generated_reports", f"report_batch_{timestamp}")
    )
        else:
            self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        # Create subdirectories for organization
        self.pdf_dir = os.path.join(self.output_dir, "pdf_reports")
        if not os.path.exists(self.pdf_dir):
            os.makedirs(self.pdf_dir)
        # Log the output directory
        print(f"Reports will be saved to: {self.output_dir}")
        self.overview_template = os.path.join("report_template", "ReportOverview.png")
        self.details_template = os.path.join("report_template", "Reports.png")
        self.additional_template = os.path.join("report_template", "AdditionalPage.png")
        # Define font styles with various sizes for different data, using DMSans for all except Roboto Mono
        # 字体大小调整，适应模板
        self.fonts = {
            "regular": {
                "small": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Regular.ttf"), 30
                ),
                "medium": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Regular.ttf"), 20
                ),
                "normal": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Regular.ttf"), 56
                ),
                "large": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Regular.ttf"), 82
                ),
                "xlarge": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Regular.ttf"), 32
                ),
            },
            "bold": {
                "small": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Bold.ttf"), 14
                ),
                "medium": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Bold.ttf"), 20
                ),
                "normal": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Bold.ttf"), 34
                ),
                "large": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Bold.ttf"), 52
                ),
                "xlarge": ImageFont.truetype(
                    os.path.join("fonts", "DMSans-Bold.ttf"), 36
                ),
            },
            # Roboto Mono fonts remain unchanged
            # 确保字体文件存在
            "roboto": {
                "regular": ImageFont.truetype(
                    os.path.join("fonts", "RobotoMono-Regular.ttf"), 24
                ),
                "bold": ImageFont.truetype(
                    os.path.join("fonts", "RobotoMono-Bold.ttf"), 30
                ),
            },
        }
        # For backward compatibility with existing code
        # 设置默认字体
        self.font_regular = self.fonts["regular"]["normal"]
        self.font_bold = self.fonts["bold"]["normal"]
        self.font_small = self.fonts["regular"]["small"]


        # Load position configuration from JSON file
        config_path = os.path.join(os.path.dirname(__file__), "pos_config.json")
        with open(config_path, "r") as f:
            self.pos_config = json.load(f)



    def generate_report(self, bill_data, store_info, orders):
        """Generate complete report PDF for a merchant"""
        store_name = store_info["name"]

        # store_info = db.get_store_info(store_id)
        
        report_id = (
            f"report_{store_info['id']}_{bill_data['start_date'].strftime('%Y%m%d')}"
        )

        # Generate overview page

        overview_page = self._generate_overview_page(bill_data, store_info)


        # 提前过滤订单，计算详情页总数

        filtered_orders = [
            order
            for order in orders
            if (order.get("payment_method") != 4 and order.get("state") == 5000)
            # 过滤 payment_method == 4 的订单 (4: Cash)，并且状态为 5000 (已完成)
        ]
        detail_count = math.ceil(len(filtered_orders) / 23)
        # 23 orders per page

        # 计算是否有额外费用
        commission = abs(
            Decimal(bill_data.get("commission_fee", 0))
            - Decimal(bill_data.get("refund_commission_fee", 0))
        )
        service = abs(Decimal(bill_data.get("service_package_fee", 0)))
        extra = abs(Decimal(bill_data.get("extra_fee", 0)))
        has_additional = commission > 0 or service > 0 or extra > 0
        overall_total = 1 + detail_count + (1 if has_additional else 0)


        # 生成详情页，向后传入整体页数
        detail_pages = self._generate_detail_pages(
            bill_data, store_info, orders, overall_total
        )
        pages = [overview_page] + detail_pages
        # 生成额外费用页
        if has_additional:
            additional_page = self._generate_additional_page(
                bill_data, store_info, detail_count + 2, overall_total
            )
            pages.append(additional_page)

        # 在合并为 PDF 之前添加页码
        pages = self._add_page_numbers(pages)

        # Combine pages into a PDF
        pdf_path = os.path.join(self.pdf_dir, f"{report_id}.pdf")
        self._combine_pages_to_pdf(pages, pdf_path)
        return pdf_path

    def _generate_overview_page(self, bill_data, store_info):
        img = Image.open(self.overview_template)
        draw = ImageDraw.Draw(img)
        import textwrap

        # 定义辅助函数，根据最大像素宽度进行换行
        def wrap_text(text, font, max_width, draw):
            words = text.split()
            lines = []
            current_line = ""
            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                w, _ = draw.textsize(test_line, font=font)
                if w <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            return "\n".join(lines)

        # --- 绘制商户名称（最大宽度500） ---
        pos_name = self.pos_config["overview"]["store_name"]
        wrapped_name = wrap_text(
            store_info["name"], self.fonts["regular"]["small"], 500, draw
        )
        draw.multiline_text(
            (pos_name["x"], pos_name["y"]),
            wrapped_name,
            fill="black",
            font=self.fonts["regular"]["small"],
            spacing=4,
        )

        # --- 绘制时间段，固定两行显示 ---
        pos_time = self.pos_config["overview"]["time_period"]
        start_line = bill_data["start_date"].strftime("%B %d, %Y")
        end_line = bill_data["end_date"].strftime("%B %d, %Y")
        draw.multiline_text(
            (pos_time["x"], pos_time["y"]),
            f"{start_line}\n{end_line}",
            fill="black",
            font=self.fonts["regular"]["small"],
            spacing=4,
        )

        # --- 绘制店铺地址（最大宽度1000） ---
        pos_address = self.pos_config["overview"]["store_address"]
        wrapped_address = wrap_text(
            store_info["address"], self.fonts["regular"]["small"], 1000, draw
        )
        draw.multiline_text(
            (pos_address["x"], pos_address["y"]),
            wrapped_address,
            fill="black",
            font=self.fonts["regular"]["small"],
            spacing=4,
        )

        # --- 其余绘制保持不变 ---

        # --- 绘制总览数据 ---

        # Orders and store amount
        pos = self.pos_config["overview"]["store_amount"]
        total_store_amount = Decimal(bill_data["store_amount"]) + Decimal(
            bill_data.get("extra_fee", 0)
        )
        draw.text(
            (pos["x"], pos["y"]),
            f"${total_store_amount:.2f}",
            fill="black",
            font=self.fonts["regular"]["large"],
        )
        pos = self.pos_config["overview"]["total_orders"]
        draw.text(
            (pos["x"], pos["y"]),
            str(bill_data["total_orders"]),
            fill="black",
            font=self.fonts["regular"]["large"],
        )

        # Sales
        pos = self.pos_config["overview"]["total_revenue"]
        draw.text(
            (pos["x"], pos["y"]),
            f"${bill_data['total_revenue']:.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )

        # Pickup tip fee
        pos = self.pos_config["overview"]["pickup_tip_fee"]
        pickup_tip_fee = bill_data.get("pickup_tip_fee", 0.0)
        draw.text(
            (pos["x"], pos["y"]),
            f"${pickup_tip_fee:.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )
        
        # Stripe fee (negative value)
        pos = self.pos_config["overview"]["stripe_fee"]
        stripe_fee = Decimal(bill_data.get("stripe_fee", 0))
        draw.text(
            (pos["x"], pos["y"]),
            f"$-{abs(stripe_fee):.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )

        # Unique users
        pos = self.pos_config["overview"]["unique_users"]
        unique_users = bill_data.get("unique_users", 0)
        draw.text(
            (pos["x"], pos["y"]),
            str(unique_users),
            fill="black",
            font=self.fonts["regular"]["large"],
        )

        # Total taxes
        pos = self.pos_config["overview"]["GST"]
        draw.text(
            (pos["x"], pos["y"]),
            f"${bill_data.get('GST', 0):.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )

        # Additional charge
        pos = self.pos_config["overview"]["Additional_charge"]
        draw.text(
            (pos["x"], pos["y"]),
            f"${bill_data.get('Additional_charge', 0):.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )

        # Total GST
        pos = self.pos_config["overview"]["GST_total"]
        draw.text(
            (pos["x"], pos["y"]),
            f"${bill_data.get('GST_total', 0):.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )

        # Total PST
        pos = self.pos_config["overview"]["PST_total"]
        draw.text(
            (pos["x"], pos["y"]),
            f"${bill_data.get('PST_total', 0):.2f}",
            fill="black",
            font=self.fonts["regular"]["normal"],
        )

        return img

    def _generate_detail_pages(self, bill_data, store_info, orders, overall_total):
        """Generate detail report pages for orders, 23 orders per page"""
        pages = []
        orders_per_page = 23
        # 过滤 payment_method == 4 的订单 (4: Cash)，并且状态为 5000 (已完成)
        filtered_orders = [
            order
            for order in orders
            if (order.get("payment_method") != 4 and order.get("state") == 5000)
        ]
        total_pages = math.ceil(len(filtered_orders) / orders_per_page)

        # 定义 payment_method 映射
        payment_method_map = {5: "Apple Pay", 7: "Card", 6: "Google Pay"}
        for page_num in range(total_pages):
            img = Image.open(self.details_template)
            draw = ImageDraw.Draw(img)
            # 获取图片宽度
            img_width, _ = img.size
            right_margin = 100  # 保留右侧100像素边距

            # -- 绘制商户名称右对齐 --
            store_name_text = store_info["name"]
            text_width, _ = draw.textsize(
                store_name_text, font=self.fonts["regular"]["small"]
            )
            x_aligned = img_width - text_width - right_margin
            # 使用配置中的 y 坐标
            pos_name = self.pos_config["detail"]["store_name"]
            draw.text(
                (x_aligned, pos_name["y"]),
                store_name_text,
                fill="black",
                font=self.fonts["regular"]["small"],
            )

            # -- 绘制时间段右对齐 --
            time_text = f"{bill_data['start_date'].strftime('%B %d, %Y')} - {bill_data['end_date'].strftime('%B %d, %Y')}"
            text_width_time, _ = draw.textsize(
                time_text, font=self.fonts["regular"]["small"]
            )
            x_aligned_time = img_width - text_width_time - right_margin
            pos_time = self.pos_config["detail"]["time_period"]
            draw.text(
                (x_aligned_time, pos_time["y"]),
                time_text,
                fill="black",
                font=self.fonts["regular"]["small"],
            )

            # --- 其余部分保持不变 ---
            pos = self.pos_config["detail"]["page_number"]
            draw.text(
                (pos["x"], pos["y"]),
                f"Page {page_num + 2}/{overall_total}",
                fill="black",
                font=self.fonts["regular"]["small"],
            )
            # 取本页订单（过滤后）
            start_idx = page_num * orders_per_page
            end_idx = min(((page_num + 1) * orders_per_page), len(filtered_orders))
            page_orders = filtered_orders[start_idx:end_idx]
            y_pos = self.pos_config["detail"]["order_start_y"]
            y_increment = self.pos_config["detail"]["order_y_increment"]
            for i, order in enumerate(page_orders):
                row_y = y_pos + (i * y_increment)
                # Order date column
                pos = self.pos_config["detail"]["order_date"]
                draw.text(
                    (pos["x"], row_y),
                    order["created_at"].strftime("%Y-%m-%d"),
                    fill="black",
                    font=self.fonts["roboto"]["bold"],
                )
                # 用户姓名列，使用 order['user_name'] 替换原 user_id
                pos = self.pos_config["detail"]["order_user_id"]
                draw.text(
                    (pos["x"], row_y),
                    str(order.get("user_name", "")),
                    fill="black",
                    font=self.fonts["roboto"]["bold"],
                )
                # Pickup code column
                pos = self.pos_config["detail"]["pickup_code"]
                draw.text(
                    (pos["x"], row_y),
                    str(order["pickup_code"]),
                    fill="black",
                    font=self.fonts["roboto"]["bold"],
                )
                # 计算最终金额及状态：
                tip = order.get("tip_fee", 0)
                refund = order.get("refund_amount", 0)
                channel = order.get("channel", 1)  # 默认1: 非取货
                if refund:
                    final_price = order["store_total_fee"] - refund
                    status_text = "Partial Refund"
                else:
                    final_price = order["store_total_fee"]
                    status_text = "Completed"
                '''
                if channel == 2:
                    final_price += tip
                # 每一行的金额不加小费
                '''

                # Order amount column with final price
                pos = self.pos_config["detail"]["order_amount"]
                amount_text = f"${final_price:.2f}"
                draw.text(
                    (pos["x"], row_y),
                    amount_text,
                    fill="black",
                    font=self.fonts["roboto"]["bold"],
                )
                # Draw status text (Final refund/completion status)
                pos = self.pos_config["detail"]["order_completed"]
                draw.text(
                    (pos["x"], row_y),
                    status_text,
                    fill="black",
                    font=self.fonts["roboto"]["bold"],
                )
                # Payment method column (映射支付名称)
                pos = self.pos_config["detail"]["order_pay_type"]
                pay_value = order.get("payment_method")
                pay_text = (
                    payment_method_map.get(pay_value, "")
                    if (pay_value is not None)
                    else ""
                )
                draw.text(
                    (pos["x"], row_y),
                    pay_text,
                    fill="black",
                    font=self.fonts["roboto"]["bold"],
                )
            pages.append(img)
        return pages

    def _generate_additional_page(
        self, bill_data, store_info, page_number, overall_total
    ):
        """Generate additional charge page based on non-zero additional charge values"""
        # 添加日志帮助调试模板文件路径
        print(f"Generating additional page using template: {self.additional_template}")
        img = Image.open(self.additional_template)
        draw = ImageDraw.Draw(img)
        pos_config = self.pos_config["additional"]

        img_width, _ = img.size
        right_margin = 50  # Adjust as needed

        # Merchant name right aligned
        merchant_text = store_info["name"]
        merchant_text_width, _ = draw.textsize(
            merchant_text, font=self.fonts["regular"]["small"]
        )
        merchant_x = img_width - merchant_text_width - right_margin
        draw.text(
            (merchant_x, pos_config["merchant_name"]["y"]),
            merchant_text,
            fill="black",
            font=self.fonts["regular"]["small"],
        )

        # Time period right aligned
        time_period_str = f"{bill_data['start_date'].strftime('%B %d, %Y')} - {bill_data['end_date'].strftime('%B %d, %Y')}"
        time_text_width, _ = draw.textsize(
            time_period_str, font=self.fonts["regular"]["small"]
        )
        time_x = img_width - time_text_width - right_margin
        draw.text(
            (time_x, pos_config["time_period"]["y"]),
            time_period_str,
            fill="black",
            font=self.fonts["regular"]["small"],
        )

        # 定义 end_date_str 供后续使用
        end_date_str = bill_data["end_date"].strftime("%B %d, %Y")

        # 准备额外费用数据行，使用 roboto 字体绘制
        rows = []
        if bill_data.get("commission_fee", 0) != 0:
            amount = bill_data.get("commission_fee", 0) - bill_data.get(
                "refund_commission_fee", 0
            )
            rows.append(("Commission Fee", f"$-{amount:.2f}", end_date_str))

        if bill_data.get("service_package_fee", 0) != 0:
            rows.append(
                (
                    "Service Package Fee",
                    f"$-{bill_data['service_package_fee']:.2f}",
                    end_date_str,
                )
            )
        if bill_data.get("extra_fee", 0) != 0:
            remark = bill_data.get("remark", "Extra Fee")
            rows.append((remark, f"${bill_data['extra_fee']:.2f}", end_date_str))

        # 绘制每一行（名称、金额、日期）以配置中的横坐标绘制，行的 y 坐标递增
        base_y = pos_config["row_start_y"]
        increment = pos_config["row_y_increment"]
        for i, (name, amount, date_text) in enumerate(rows):
            row_y = base_y + (i * increment)
            # Commission row：名称使用 pos_config["commission_fee"]["name"]等（其它行类似）
            # 根据费用类型选择对应的 x 坐标
            if name in ["Commission Fee"]:
                name_x = pos_config["commission_fee"]["name"]["x"]
                amount_x = pos_config["commission_fee"]["amount"]["x"]
                date_x = pos_config["commission_fee"]["date"]["x"]
            elif name in ["Service Package Fee"]:
                name_x = pos_config["service_package_fee"]["name"]["x"]
                amount_x = pos_config["service_package_fee"]["amount"]["x"]
                date_x = pos_config["service_package_fee"]["date"]["x"]
            else:
                name_x = pos_config["extra_fee"]["name"]["x"]
                amount_x = pos_config["extra_fee"]["amount"]["x"]
                date_x = pos_config["extra_fee"]["date"]["x"]
            draw.text(
                (name_x, row_y), name, fill="black", font=self.fonts["roboto"]["bold"]
            )
            draw.text(
                (amount_x, row_y),
                amount,
                fill="black",
                font=self.fonts["roboto"]["bold"],
            )
            draw.text(
                (date_x, row_y),
                date_text,
                fill="black",
                font=self.fonts["roboto"]["bold"],
            )

        return img

    def _combine_pages_to_pdf(self, images, output_path):
        """Convert a list of PIL images to a single PDF file"""
        pdf_writer = PyPDF2.PdfWriter()
        for img in images:
            # Convert RGBA to RGB mode before saving as PDF
            if img.mode == "RGBA":
                # Create a white background image
                bg = Image.new("RGB", img.size, (255, 255, 255))
                # Paste the RGBA image on the white background, using alpha as mask
                bg.paste(img, (0, 0), img.split()[3])  # 3 is the alpha channel
                img = bg
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="PDF")
            img_byte_arr.seek(0)
            pdf_reader = PyPDF2.PdfReader(img_byte_arr)
            pdf_writer.add_page(pdf_reader.pages[0])
        with open(output_path, "wb") as f:
            pdf_writer.write(f)

    def _add_page_numbers(self, pages):
        """在所有页面添加页码"""
        total_pages = len(pages)
        for i, img in enumerate(pages):
            draw = ImageDraw.Draw(img)
            page_num = i + 1
            # 使用 detail 中的 page_number 坐标
            pos = self.pos_config["detail"]["page_number"]
            draw.text(
                (pos["x"], pos["y"]),
                f"Page {page_num}/{total_pages}",
                fill="black",
                font=self.fonts["regular"]["small"],
            )
        return pages
