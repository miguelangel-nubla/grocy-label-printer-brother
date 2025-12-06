# Grocy Label Printer Brother

A Flask server that receives Grocy label requests and prints them to Brother QL thermal printers.

## Features

- **Grocy Integration**: Compatible with Grocy's label printing system via webhooks.
- **Brother QL Support**: Works with Brother QL series printers (USB and Network/WiFi).
- **Auto-Detection**: Automatically detects label size for PT series printers connected via network.
- **Smart Layout**:
  - **Endless Labels**: Barcode on the left, text on the right.
  - **Die-Cut Labels**: Optimized layout for fixed sizes.
- **Configurable Fonts**: Customizable fonts and sizes for product names and dates.
- **Container Support**: Docker-ready for easy deployment.

## Quick Start

### Docker (Recommended)

```bash
docker run -d \
  --name grocy-label-printer \
  -p 5000:80 \
  -e PRINTER_PATH="tcp://192.168.1.100" \
  -e PRINTER_MODEL="PT-P750W" \
  ghcr.io/miguelangel-nubla/grocy-label-printer-brother:latest
```

### Manual Setup

1.  Clone the repository:
    ```bash
    git clone https://github.com/miguelangel-nubla/grocy-label-printer-brother.git
    cd grocy-label-printer-brother
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3.  Run the server:
    ```bash
    gunicorn --conf gunicorn_conf.py --bind 0.0.0.0:5000 app:app
    ```

## Configuration

### Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PRINTER_MODEL` | `QL-500` | Brother printer model (e.g., `QL-700`, `PT-P750W`). |
| `PRINTER_PATH` | `file:///dev/usb/lp1` | Connection path: `tcp://IP_ADDRESS` or `file:///dev/usb/lpX`. |
| `LABEL_SIZE` | *None* | Label identifier (e.g., `62`, `29x90`). **Required** unless auto-detected (PT network printers). |
| `PRINTER_600DPI` | `true` | Set to `true` for high-resolution printing. |
| `BARCODE_FORMAT` | `Datamatrix` | Barcode format (e.g., `QR`, `Datamatrix`, `Code128`). |
| `NAME_FONT` | `NotoSerif-Regular.ttf` | Font file for product name (placed in `fonts/`). |
| `NAME_FONT_SIZE` | `48` | Font size for product name. |
| `NAME_MAX_LINES` | `4` | Maximum lines for product name wrapping. |
| `DUE_DATE_FONT` | *Same as NAME_FONT* | Font file for dates/amounts. |
| `DUE_DATE_FONT_SIZE` | `30` | Font size for dates/amounts. |

### Grocy Configuration

In Grocy, configure a new label printer:

1.  Go to **Manage > Label printers**.
2.  Add a new printer with these settings:
    -   **Name**: Brother Label Printer
    -   **Type**: Webhook
    -   **URL**: `http://your-server:5000/print`
    -   **JSON payload**:
        ```json
        {
          "product": "{{ product }}",
          "grocycode": "{{ grocycode }}",
          "best_before_date": "{{ best_before_date }}",
          "purchased_date": "{{ purchased_date }}",
          "amount": "{{ amount }}",
          "note": "{{ note }}",
          "stock_entry": {
             "best_before_date": "{{ best_before_date }}",
             "purchased_date": "{{ purchased_date }}",
             "amount": "{{ amount }}",
             "note": "{{ note }}"
          }
        }
        ```

## API Endpoints

### `POST /print`
Print a label using the provided data.

**Request Body** (JSON):
```json
{
  "product": "Product Name",
  "grocycode": "grcy:...",
  "stock_entry": {
    "best_before_date": "2023-12-31",
    "amount": "1.5"
  }
}
```

### `GET /image`
Generate and return a preview of the label image (PNG). Useful for testing layout without printing.

**Parameters** (Query String):
- `product`: Product name
- `grocycode`: Barcode content
- `amount`: Quantity
- ... (same fields as JSON body)

### `GET /`
Returns the current label configuration status.

**Response**: `Label <size_id>, <size_name>`

## Label Format

The label layout is dynamically generated based on the label size:

-   **Endless Labels** (e.g., 62mm continuous):
    -   **Barcode**: Placed on the left side.
    -   **Product Name**: Wrapped text on the right side.
    -   **Metadata**: Amount and dates are intelligently placed to maximize space usage.
-   **Die-Cut Labels**:
    -   Layout adapts to fixed dimensions, scaling the barcode and text to fit.