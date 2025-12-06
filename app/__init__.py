from io import BytesIO
from os import path, getenv
import logging
import re
from flask import Flask, Response, request
from PIL import ImageFont
from dotenv import load_dotenv
from brother_ql.labels import ALL_LABELS, Color
from brother_ql import BrotherQLRaster, create_label
from brother_ql.backends import guess_backend, backend_factory
from app.imaging import create_barcode, create_label_image

load_dotenv()

def _get_pt_label_size(printer_path):
    """Auto-detect PT printer label size from web interface."""
    try:
        # Extract IP from printer path (tcp://10.2.3.135 -> 10.2.3.135)
        ip_match = re.search(r'tcp://([0-9.]+)', printer_path)
        if not ip_match:
            return None
            
        printer_ip = ip_match.group(1)
        
        from urllib.request import urlopen
        from urllib.error import URLError
        import socket
        
        url = f"http://{printer_ip}/general/status.html"
        
        # Set timeout for the request
        with urlopen(url, timeout=5) as response:
            html_content = response.read().decode('utf-8')
        
        # Extract media type from HTML
        media_match = re.search(r'<dt>Media.*?Type</dt>\s*<dd>(\d+)mm', html_content, re.IGNORECASE | re.DOTALL)
        
        if media_match:
            width_mm = int(media_match.group(1))
            return f"pt{width_mm}"
        
        return None
        
    except (URLError, socket.timeout, ValueError, AttributeError):
        return None

class Config:
    """Application configuration."""
    PRINTER_MODEL = getenv("PRINTER_MODEL", "QL-500")
    PRINTER_PATH = getenv("PRINTER_PATH", "file:///dev/usb/lp1")
    PRINTER_600DPI = getenv("PRINTER_600DPI", "true").lower() == "true"
    LABEL_SIZE = getenv("LABEL_SIZE")  # Optional fallback, can be None for PT printers
    BARCODE_FORMAT = getenv("BARCODE_FORMAT", "Datamatrix")
    NAME_FONT = getenv("NAME_FONT", "NotoSerif-Regular.ttf")
    NAME_FONT_SIZE = int(getenv("NAME_FONT_SIZE", "48"))
    NAME_MAX_LINES = int(getenv("NAME_MAX_LINES", "4"))
    DUE_DATE_FONT = getenv("DUE_DATE_FONT", getenv("NAME_FONT", "NotoSerif-Regular.ttf"))
    DUE_DATE_FONT_SIZE = int(getenv("DUE_DATE_FONT_SIZE", "30"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize printer configuration
selected_backend = guess_backend(Config.PRINTER_PATH)
BACKEND_CLASS = backend_factory(selected_backend)['backend_class']

def _get_current_label_size_and_spec():
    """Get current label size and spec, detecting PT printer size if needed."""
    # For PT printers with TCP connection, auto-detect label size
    if Config.PRINTER_MODEL.startswith("PT-") and Config.PRINTER_PATH.startswith("tcp://"):
        detected_size = _get_pt_label_size(Config.PRINTER_PATH)
        if detected_size:
            label_size = detected_size
        elif Config.LABEL_SIZE:
            label_size = Config.LABEL_SIZE
        else:
            raise ValueError("PT printer label size could not be detected and LABEL_SIZE environment variable not set")
    else:
        # For non-PT printers, use environment variable
        if not Config.LABEL_SIZE:
            raise ValueError("LABEL_SIZE environment variable not set")
        label_size = Config.LABEL_SIZE
    
    # Get label spec from size
    label_spec = next(x for x in ALL_LABELS if x.identifier == label_size)
    return label_size, label_spec

# Load fonts
thisDir = path.dirname(path.abspath(__file__))
nameFont = ImageFont.truetype(path.join(thisDir, "..", "fonts", Config.NAME_FONT), Config.NAME_FONT_SIZE)
ddFont = ImageFont.truetype(path.join(thisDir, "..", "fonts", Config.DUE_DATE_FONT), Config.DUE_DATE_FONT_SIZE)

app = Flask(__name__)

@app.before_request
def log_post_json_requests():
    if request.method == "POST" and request.is_json:
        json_data = request.get_json()
        endpoint = request.endpoint or request.path
        logging.info(f"POST JSON Request to {endpoint} - Data: {json_data}")

@app.route("/")
def home_route():
    try:
        _, label_spec = _get_current_label_size_and_spec()
        return "Label %s, %s"%(label_spec.identifier, label_spec.name)
    except ValueError as e:
        return f"Configuration error: {e}", 500

def get_params():
    """Extract and validate parameters from request."""
    # Handle different data sources
    if request.method == "POST" and request.is_json:
        source = request.get_json()
        logging.debug(f"POST JSON request - Data: {source}")
    elif request.method == "POST":
        source = request.form
        logging.debug(f"POST form request - Data: {dict(source)}")
    else:
        source = request.args
        logging.debug(f"GET request - Query params: {dict(source)}")

    # Extract name from various fields
    name_fields = ['product', 'battery', 'chore', 'recipe']
    name = next((source.get(field, '') for field in name_fields if source.get(field)), '')
    
    barcode = source.get('grocycode', '')
    
    # Extract stock entry data
    stock_entry = source.get('stock_entry') or {}
    if not isinstance(stock_entry, dict):
        stock_entry = {}
    
    # Check for special case: stock_entry_userfields with StockEntryContainerWeight
    stock_entry_userfields = source.get('stock_entry_userfields') or {}
    container_weight = stock_entry_userfields.get('StockEntryContainerWeight')
    
    # If StockEntryContainerWeight is a valid number, exclude amount and dates
    exclude_amount_and_dates = False
    if container_weight is not None:
        try:
            float(container_weight)
            exclude_amount_and_dates = True
        except (ValueError, TypeError):
            pass
    
    label_fields = {
        'best_before_date': '' if exclude_amount_and_dates else (str(stock_entry.get('best_before_date', '')) if stock_entry.get('best_before_date') else ''),
        'purchased_date': '' if exclude_amount_and_dates else (str(stock_entry.get('purchased_date', '')) if stock_entry.get('purchased_date') else ''),
        'amount': '' if exclude_amount_and_dates else (str(stock_entry.get('amount', '')) if stock_entry.get('amount') else ''),
        'note': str(stock_entry.get('note', ''))
    }
    
    # Extract unit info
    quantity_unit_stock = (
        source.get('quantity_unit_stock') if isinstance(source.get('quantity_unit_stock'), dict)
        else source.get('details', {}).get('quantity_unit_stock', {})
    )
    
    unit_name = _get_unit_name(quantity_unit_stock, label_fields['amount'])
    
    logging.debug(f"Extracted - name: '{name}', barcode: '{barcode}', label_fields: {label_fields}, unit: '{unit_name}'")
    return (name, barcode, label_fields['best_before_date'], label_fields['purchased_date'], label_fields['amount'], unit_name, label_fields['note'])

def _get_unit_name(quantity_unit_stock, amount):
    """Get appropriate unit name (singular/plural)."""
    if not quantity_unit_stock.get('name'):
        return ''
    
    try:
        amount_float = float(amount) if amount else 0
        if amount_float > 1 and quantity_unit_stock.get('name_plural'):
            return str(quantity_unit_stock['name_plural'])
        return str(quantity_unit_stock['name'])
    except (ValueError, TypeError):
        return str(quantity_unit_stock.get('name', ''))

@app.route("/print", methods=["GET", "POST"])
def print_route():
    """Generate and print a label."""
    logging.debug(f"Print endpoint: {request.method} {request.url}")
    params = get_params()
    label = _create_label(*params)
    sendToPrinter(label)
    logging.debug("Label sent to printer successfully")
    return Response("OK", 200)

@app.route("/image", methods=["GET", "POST"])
def image_route():
    """Generate and return label image."""
    logging.debug(f"Image endpoint: {request.method} {request.url}")
    params = get_params()
    img = _create_label(*params)
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    logging.debug("Label image generated successfully")
    return Response(buf, 200, mimetype="image/png")

def _create_label(name, barcode_text, best_before_date, purchased_date, amount, unit_name, note):
    """Create label image with given parameters."""
    _, label_spec = _get_current_label_size_and_spec()
    barcode = create_barcode(barcode_text, Config.BARCODE_FORMAT)
    return create_label_image(
        label_spec.dots_total, name, nameFont, Config.NAME_MAX_LINES,
        barcode, best_before_date, purchased_date, amount, unit_name, note, ddFont
    )

def sendToPrinter(image):
    """Send image to Brother QL printer."""
    label_size, label_spec = _get_current_label_size_and_spec()
    bql = BrotherQLRaster(Config.PRINTER_MODEL)
    bql.dpi_600 = Config.PRINTER_600DPI
    
    create_label(
        bql, image, label_size,
        red=(label_spec.color == Color.BLACK_RED_WHITE)
    )
    
    backend = BACKEND_CLASS(Config.PRINTER_PATH)
    backend.write(bql.data)
    backend.dispose() if hasattr(backend, 'dispose') else None
