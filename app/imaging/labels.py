"""Label generation and layout utilities."""

from typing import Tuple, NamedTuple
from PIL import Image, ImageFont, ImageDraw
from .text import wrap_text


class LabelConfig(NamedTuple):
    """Configuration for label generation."""
    label_size: Tuple[int, int]
    text: str
    text_font: ImageFont.FreeTypeFont
    text_max_lines: int
    barcode: Image.Image
    best_before_date: str = ""
    purchased_date: str = ""
    amount: str = ""
    unit_name: str = ""
    note: str = ""
    due_date_font: ImageFont.FreeTypeFont = None


class LabelLayout:
    """Handles label layout calculations and rendering."""
    
    def __init__(self, config: LabelConfig):
        self.config = config
        self.is_endless = config.label_size[1] == 0
        self.height, self.width = config.label_size if self.is_endless else (config.label_size[1], config.label_size[0])
        self.line_spacing = 4
        self.due_date_font = config.due_date_font or config.text_font
        
    def create_label(self) -> Image.Image:
        """Create the complete label image."""
        # Process barcode
        barcode = self._process_barcode()
        
        # Calculate width for endless labels
        if self.width == 0:
            self.width = self._calculate_endless_width(barcode)
        
        # Create base label
        label = Image.new("RGB", (self.width, self.height), "white")
        self._place_barcode(label, barcode)
        
        # Add text and metadata
        draw = ImageDraw.Draw(label)
        self._draw_content(draw, barcode)
        
        return label.rotate(-90, expand=True) if self.is_endless else label
    
    def _process_barcode(self) -> Image.Image:
        """Scale barcode appropriately for label type."""
        if self.is_endless:
            return self._scale_barcode_endless()
        return self._scale_barcode_fixed()
    
    def _scale_barcode_endless(self) -> Image.Image:
        """Scale barcode to fit endless label height."""
        scale_factor = self.height / self.config.barcode.size[1]
        new_size = (
            int(self.config.barcode.size[0] * scale_factor),
            int(self.config.barcode.size[1] * scale_factor)
        )
        return self.config.barcode.resize(new_size, Image.Resampling.NEAREST)
    
    def _scale_barcode_fixed(self) -> Image.Image:
        """Scale barcode for fixed label dimensions."""
        barcode = self.config.barcode
        max_barcode_width = self.width // 2
        
        if self.height > (self.height * 0.4) and barcode.size[0] <= max_barcode_width:
            for scale in [8, 6, 4, 2]:
                scaled_size = (barcode.size[0] * scale, barcode.size[1] * scale)
                if (scaled_size[1] < self.height and scaled_size[0] <= max_barcode_width):
                    return barcode.resize(scaled_size, Image.Resampling.NEAREST)
        return barcode
    
    def _calculate_endless_width(self, barcode: Image.Image) -> int:
        """Calculate width for endless labels."""
        name_text, name_text_width = wrap_text(
            self.config.text, self.config.text_font, 1000, self.config.text_max_lines
        )
        
        date_display = self._create_date_display()
        amount_display = self._create_amount_display()
        
        text_width_needed = name_text_width
        if date_display:
            text_width_needed = max(text_width_needed, self.due_date_font.getlength(date_display))
        if amount_display:
            text_width_needed = max(text_width_needed, self.due_date_font.getlength(amount_display))
        
        gap = self.config.text_font.size // 2
        
        # If no text or metadata, return just the barcode width
        if text_width_needed == 0:
            return barcode.size[0]
            
        calculated_width = int(barcode.size[0] + gap + text_width_needed)
        min_width = barcode.size[0] + int(self.height * 0.4)
        
        return max(calculated_width, min_width)
    
    def _place_barcode(self, label: Image.Image, barcode: Image.Image) -> None:
        """Place barcode on the label."""
        barcode_y = 0 if self.is_endless else (self.height - barcode.size[1]) // 2
        label.paste(barcode, (0, barcode_y))
    
    def _draw_content(self, draw: ImageDraw.ImageDraw, barcode: Image.Image) -> None:
        """Draw text and metadata on the label."""
        self._draw_main_text(draw, barcode)
        self._draw_metadata(draw, barcode)
    
    def _draw_main_text(self, draw: ImageDraw.ImageDraw, barcode: Image.Image) -> None:
        """Draw the main product text."""
        if self.is_endless:
            name_text = self.config.text
            text_x = barcode.size[0] + self.config.text_font.size // 2
            text_align = "left"
            text_y = self._calculate_text_y_endless(name_text)
        else:
            name_text, _ = wrap_text(
                self.config.text, self.config.text_font,
                self.width - barcode.size[0], self.config.text_max_lines
            )
            text_width = self.config.text_font.getlength(name_text.split('\n')[0])
            text_x = barcode.size[0] + (self.width - barcode.size[0] - text_width) // 2
            text_align = "center"
            text_y = 0
        
        draw.multiline_text(
            (text_x, text_y), name_text, fill="black",
            font=self.config.text_font, align=text_align, spacing=self.line_spacing
        )
    
    def _draw_metadata(self, draw: ImageDraw.ImageDraw, barcode: Image.Image) -> None:
        """Draw amount and date information."""
        amount_display = self._create_amount_display()
        date_display = self._create_date_display()
        
        if amount_display:
            self._draw_amount(draw, amount_display)
        
        if date_display:
            self._draw_date(draw, date_display, barcode)
    
    def _draw_amount(self, draw: ImageDraw.ImageDraw, amount_display: str) -> None:
        """Draw amount in top right corner."""
        amount_width = self.due_date_font.getlength(amount_display)
        amount_x = self.width - amount_width
        draw.text((amount_x, 0), amount_display, fill="black", font=self.due_date_font)
    
    def _draw_date(self, draw: ImageDraw.ImageDraw, date_display: str, barcode: Image.Image) -> None:
        """Draw date information."""
        date_width = self.due_date_font.getlength(date_display)
        _, _, _, date_height = self.due_date_font.getbbox(date_display)
        
        if self.is_endless:
            text_width = self.config.text_font.getlength(self.config.text)
            text_x = barcode.size[0] + self.config.text_font.size // 2
            date_x = text_x if date_width > text_width else text_x + text_width - date_width
            date_y = self.height - date_height
        else:
            date_x = self.width - date_width
            date_y = self.height - date_height
        
        draw.text((date_x, date_y), date_display, fill="black", font=self.due_date_font)
    
    def _calculate_text_y_endless(self, text: str) -> int:
        """Calculate Y position for text in endless labels."""
        amount_display = self._create_amount_display()
        date_display = self._create_date_display()
        
        if amount_display and not date_display:
            amount_height = self.due_date_font.size
            available_height = self.height - amount_height
            _, text_top, _, text_bottom = self.config.text_font.getbbox(text)
            text_height = text_bottom - text_top
            return amount_height + (available_height - text_height) // 2 - text_top
        elif not date_display and not amount_display:
            _, text_top, _, text_bottom = self.config.text_font.getbbox(text)
            text_height = text_bottom - text_top
            return (self.height - text_height) // 2 - text_top
        else:
            return self.due_date_font.size if amount_display else 0
    
    def _create_date_display(self) -> str:
        """Create formatted date display string."""
        purchased = self.config.purchased_date
        best_before = self.config.best_before_date
        note = self.config.note
        
        parts = []
        if note:
            parts.append(note)
            parts.append("|")
        if purchased:
            parts.append(purchased)
        if best_before:
            if purchased:
                parts.append("-")
            parts.append(best_before)
            
        return " ".join(parts)
    
    def _create_amount_display(self) -> str:
        """Create formatted amount display string."""
        amount = self.config.amount
        unit = self.config.unit_name
        
        if amount and unit:
            return f"{amount} {unit}"
        return amount or ""


def create_label_image(label_size: Tuple[int, int], text: str,
                      text_font: ImageFont.FreeTypeFont, text_max_lines: int,
                      barcode: Image.Image, best_before_date: str = "",
                      purchased_date: str = "", amount: str = "",
                      unit_name: str = "", note: str = "", due_date_font: ImageFont.FreeTypeFont = None) -> Image.Image:
    """Create a label image with barcode, text, and optional date/amount info."""
    config = LabelConfig(
        label_size=label_size,
        text=text,
        text_font=text_font,
        text_max_lines=text_max_lines,
        barcode=barcode,
        best_before_date=best_before_date,
        purchased_date=purchased_date,
        amount=amount,
        unit_name=unit_name,
        note=note,
        due_date_font=due_date_font
    )
    
    layout = LabelLayout(config)
    return layout.create_label()