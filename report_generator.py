import os
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
        
        # Define font styles (adjust paths to your font files)
        self.font_regular = ImageFont.truetype("arial.ttf", 24)
        self.font_bold = ImageFont.truetype("arialbd.ttf", 26)
        self.font_small = ImageFont.truetype("arial.ttf", 18)
    
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
        
        # Add text to the template
        # Store name
        # Comment: Position X: 350, Y: 150
        draw.text((350, 150), store_info['name'], fill="black", font=self.font_bold)
        
        # Store address
        # Comment: Position X: 350, Y: 190
        draw.text((350, 190), store_info['address'], fill="black", font=self.font_regular)
        
        # Time period
        # Comment: Position X: 350, Y: 250
        time_period = f"{bill_data['start_date'].strftime('%B %d, %Y')} - {bill_data['end_date'].strftime('%B %d, %Y')}"
        draw.text((350, 250), time_period, fill="black", font=self.font_regular)
        
        # Settlement amount
        # Comment: Position X: 600, Y: 400
        draw.text((600, 400), f"${bill_data['settlement_amount']:.2f}", fill="black", font=self.font_bold)
        
        # Total orders
        # Comment: Position X: 350, Y: 480
        draw.text((350, 480), str(bill_data['total_orders']), fill="black", font=self.font_regular)
        
        # Total revenue
        # Comment: Position X: 600, Y: 480
        draw.text((600, 480), f"${bill_data['total_revenue']:.2f}", fill="black", font=self.font_regular)
        
        # Return the generated image
        return img
    
    def _generate_detail_pages(self, bill_data, store_info, orders):
        """Generate detail report pages for orders, 40 orders per page"""
        pages = []
        orders_per_page = 40
        total_pages = math.ceil(len(orders) / orders_per_page)
        
        for page_num in range(total_pages):
            img = Image.open(self.details_template)
            draw = ImageDraw.Draw(img)
            
            # Add store name and time period to each page
            # Comment: Position X: 350, Y: 80
            draw.text((350, 80), store_info['name'], fill="black", font=self.font_bold)
            
            # Comment: Position X: 350, Y: 120
            time_period = f"{bill_data['start_date'].strftime('%B %d, %Y')} - {bill_data['end_date'].strftime('%B %d, %Y')}"
            draw.text((350, 120), time_period, fill="black", font=self.font_regular)
            
            # Add page number
            # Comment: Position X: 700, Y: 80
            draw.text((700, 80), f"Page {page_num + 1}/{total_pages}", fill="black", font=self.font_small)
            
            # Get orders for this page
            start_idx = page_num * orders_per_page
            end_idx = min((page_num + 1) * orders_per_page, len(orders))
            page_orders = orders[start_idx:end_idx]
            
            # Starting Y position for the first order
            # Comment: Starting Y position for orders table
            y_pos = 200
            y_increment = 30
            
            for i, order in enumerate(page_orders):
                # Comment: Order row positions
                row_y = y_pos + (i * y_increment)
                
                # Order date (column 1)
                # Comment: Date column X: 100
                draw.text((100, row_y), order['created_at'].strftime("%Y-%m-%d"), fill="black", font=self.font_small)
                
                # Pickup code (column 2)
                # Comment: Pickup code column X: 300
                draw.text((300, row_y), str(order['pickup_code']), fill="black", font=self.font_small)
                
                # Order amount (column 3)
                # Comment: Amount column X: 600
                draw.text((600, row_y), f"${order['store_total_fee']:.2f}", fill="black", font=self.font_small)
            
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
