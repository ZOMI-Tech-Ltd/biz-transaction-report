import os
import json
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import PyPDF2
import io
import math
import datetime

class ReportGenerator:
    def __init__(self, output_dir=None):
        # Create a timestamp-based reports folder if none specified
        if output_dir is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = os.path.abspath(os.path.join(
                "e:", "ZOMI", "biz-transaction-report", "generated_reports", 
                f"report_batch_{timestamp}"
            ))
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
        
        # Define font styles with various sizes for different data
        # You can adjust these sizes as needed
        self.fonts = {
            # Font sizes for regular text
            'regular': {
                'small': ImageFont.truetype("arial.ttf", 14),
                'medium': ImageFont.truetype("arial.ttf", 20),
                'normal': ImageFont.truetype("arial.ttf", 24),
                'large': ImageFont.truetype("arial.ttf", 28),
                'xlarge': ImageFont.truetype("arial.ttf", 32)
            },
            # Font sizes for bold text
            'bold': {
                'small': ImageFont.truetype("arialbd.ttf", 14),
                'medium': ImageFont.truetype("arialbd.ttf", 20),
                'normal': ImageFont.truetype("arialbd.ttf", 26),
                'large': ImageFont.truetype("arialbd.ttf", 52),
                'xlarge': ImageFont.truetype("arialbd.ttf", 36)
            }
        }
        
        # For backward compatibility with existing code
        self.font_regular = self.fonts['regular']['normal']
        self.font_bold = self.fonts['bold']['normal']  
        self.font_small = self.fonts['regular']['small']

        # Load position configuration from JSON file
        config_path = os.path.join(os.path.dirname(__file__), 'pos_config.json')
        with open(config_path, 'r') as f:
            self.pos_config = json.load(f)
    
    def generate_report(self, bill_data, store_info, orders):
        """Generate complete report PDF for a merchant"""
        store_name = store_info['name']
        report_id = f"report_{store_info['id']}_{bill_data['start_date'].strftime('%Y%m%d')}"
        
        # Generate overview page
        overview_page = self._generate_overview_page(bill_data, store_info)
        
        # Generate detail pages
        detail_pages = self._generate_detail_pages(bill_data, store_info, orders)
        
        # Combine pages into a PDF
        pdf_path = os.path.join(self.pdf_dir, f"{report_id}.pdf")
        self._combine_pages_to_pdf([overview_page] + detail_pages, pdf_path)
        
        return pdf_path
    
    def _generate_overview_page(self, bill_data, store_info):
        """Generate overview report page for a merchant"""
        img = Image.open(self.overview_template)
        draw = ImageDraw.Draw(img)
        
        # Draw store name using JSON params
        pos = self.pos_config['overview']['store_name']
        draw.text((pos['x'], pos['y']), store_info['name'], fill="black", font=self.fonts['bold']['large'])
        
        # Draw store address
        pos = self.pos_config['overview']['store_address']
        draw.text((pos['x'], pos['y']), store_info['address'], fill="black", font=self.fonts['bold']['large'])
        
        # Draw time period
        pos = self.pos_config['overview']['time_period']
        time_period = f"{bill_data['start_date'].strftime('%B %d, %Y')} - {bill_data['end_date'].strftime('%B %d, %Y')}"
        draw.text((pos['x'], pos['y']), time_period, fill="black", font=self.fonts['bold']['large'])
        
        # Draw settlement amount
        pos = self.pos_config['overview']['settlement_amount']
        draw.text((pos['x'], pos['y']), f"${bill_data['settlement_amount']:.2f}", fill="black", font=self.fonts['bold']['large'])
        
        # Draw total orders
        pos = self.pos_config['overview']['total_orders']
        draw.text((pos['x'], pos['y']), str(bill_data['total_orders']), fill="black", font=self.fonts['bold']['large'])
        
        # Draw total revenue
        pos = self.pos_config['overview']['total_revenue']
        draw.text((pos['x'], pos['y']), f"${bill_data['total_revenue']:.2f}", fill="black", font=self.fonts['bold']['large'])
        
        # Draw pickup_tip_fee with default 0.0 if missing
        pos = self.pos_config['overview']['pickup_tip_fee']
        pickup_tip_fee = bill_data.get('pickup_tip_fee', 0.0)
        draw.text((pos['x'], pos['y']), f"${pickup_tip_fee:.2f}", fill="black", font=self.fonts['bold']['large'])
        
        # Draw stripe_fee with default 0.0 if missing
        pos = self.pos_config['overview']['stripe_fee']
        stripe_fee = bill_data.get('stripe_fee', 0.0)
        draw.text((pos['x'], pos['y']), f"${stripe_fee:.2f}", fill="black", font=self.fonts['bold']['large'])
        
        # Draw unique_users with default 0 if missing
        pos = self.pos_config['overview']['unique_users']
        unique_users = bill_data.get('unique_users', 0)
        draw.text((pos['x'], pos['y']), str(unique_users), fill="black", font=self.fonts['bold']['large'])
        
        # Return the generated image
        return img
    
    def _generate_detail_pages(self, bill_data, store_info, orders):
        """Generate detail report pages for orders, 23 orders per page"""
        pages = []
        orders_per_page = 23
        # 过滤 payment_method == 4 的订单
        filtered_orders = [order for order in orders if order.get('payment_method') != 4]
        total_pages = math.ceil(len(filtered_orders) / orders_per_page)
        
        # 定义 payment_method 映射
        payment_method_map = {5: "Apple Pay", 7: "Card", 6: "Google Pay"}
        
        for page_num in range(total_pages):
            img = Image.open(self.details_template)
            draw = ImageDraw.Draw(img)
            
            # Draw store name in details page
            pos = self.pos_config['detail']['store_name']
            draw.text((pos['x'], pos['y']), store_info['name'], fill="black", font=self.fonts['bold']['large'])
            
            # Draw time period in details page
            pos = self.pos_config['detail']['time_period']
            time_period = f"{bill_data['start_date'].strftime('%B %d, %Y')} - {bill_data['end_date'].strftime('%B %d, %Y')}"
            draw.text((pos['x'], pos['y']), time_period, fill="black", font=self.fonts['bold']['large'])
            
            # Draw page number
            pos = self.pos_config['detail']['page_number']
            draw.text((pos['x'], pos['y']), f"Page {page_num + 1}/{total_pages}", fill="black", font=self.fonts['bold']['large'])
            
            # 取本页订单（过滤后）
            start_idx = page_num * orders_per_page
            end_idx = min((page_num + 1) * orders_per_page, len(filtered_orders))
            page_orders = filtered_orders[start_idx:end_idx]
            
            y_pos = self.pos_config['detail']['order_start_y']
            y_increment = self.pos_config['detail']['order_y_increment']
            
            for i, order in enumerate(page_orders):
                row_y = y_pos + (i * y_increment)
                
                # Order date column
                pos = self.pos_config['detail']['order_date']
                draw.text((pos['x'], row_y), order['created_at'].strftime("%Y-%m-%d"), fill="black", font=self.fonts['bold']['large'])
                
                # 用户姓名列，使用 order['user_name'] 替换原 user_id
                pos = self.pos_config['detail']['order_user_id']
                draw.text((pos['x'], row_y), str(order.get('user_name', '')), fill="black", font=self.fonts['bold']['large'])
                
                # Pickup code column
                pos = self.pos_config['detail']['pickup_code']
                draw.text((pos['x'], row_y), str(order['pickup_code']), fill="black", font=self.fonts['bold']['large'])
                
                # Order amount column with Completed text
                pos = self.pos_config['detail']['order_amount']
                amount_text = f"${order['store_total_fee']:.2f}"
                draw.text((pos['x'], row_y), amount_text, fill="black", font=self.fonts['bold']['large'])
                
                # Draw "Completed" next to order amount
                pos = self.pos_config['detail']['order_completed']
                draw.text((pos['x'], row_y), "Completed", fill="black", font=self.fonts['bold']['large'])
                
                # Payment method column (映射支付名称)
                pos = self.pos_config['detail']['order_pay_type']
                pay_value = order.get('payment_method')
                pay_text = payment_method_map.get(pay_value, "") if pay_value is not None else ""
                draw.text((pos['x'], row_y), pay_text, fill="black", font=self.fonts['bold']['large'])
            
            pages.append(img)
        
        return pages
    
    def _combine_pages_to_pdf(self, images, output_path):
        """Convert a list of PIL images to a single PDF file"""
        pdf_writer = PyPDF2.PdfWriter()
        
        for img in images:
            # Convert RGBA to RGB mode before saving as PDF
            if img.mode == 'RGBA':
                # Create a white background image
                bg = Image.new('RGB', img.size, (255, 255, 255))
                # Paste the RGBA image on the white background, using alpha as mask
                bg.paste(img, (0, 0), img.split()[3])  # 3 is the alpha channel
                img = bg
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PDF')
            img_byte_arr.seek(0)
            
            pdf_reader = PyPDF2.PdfReader(img_byte_arr)
            pdf_writer.add_page(pdf_reader.pages[0])
        
        with open(output_path, 'wb') as f:
            pdf_writer.write(f)
