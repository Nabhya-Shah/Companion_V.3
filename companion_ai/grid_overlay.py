from PIL import Image, ImageDraw, ImageFont
import math

class GridOverlay:
    """
    Utility to overlay a numbered grid on an image for precise targeting by AI.
    """
    
    @staticmethod
    def overlay_grid(image: Image.Image, rows=5, cols=5):
        """
        Draws a grid on the image and returns:
        1. The modified image
        2. A dictionary mapping grid_id (int) -> (center_x, center_y)
        """
        draw = ImageDraw.Draw(image)
        width, height = image.size
        
        cell_w = width / cols
        cell_h = height / rows
        
        grid_map = {}
        
        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype("arial.ttf", size=int(min(cell_w, cell_h)/4))
        except IOError:
            font = ImageDraw.getdraw(image).getfont()

        count = 1
        for r in range(rows):
            for c in range(cols):
                # Calculate bounds
                x1 = c * cell_w
                y1 = r * cell_h
                x2 = x1 + cell_w
                y2 = y1 + cell_h
                
                # Draw rect
                draw.rectangle([x1, y1, x2, y2], outline="red", width=2)
                
                # Draw number in center
                center_x = int((x1 + x2) / 2)
                center_y = int((y1 + y2) / 2)
                
                text = str(count)
                
                # Draw text with simple background for visibility
                text_bbox = draw.textbbox((center_x, center_y), text, font=font)
                w_text = text_bbox[2] - text_bbox[0]
                h_text = text_bbox[3] - text_bbox[1]
                
                draw.rectangle(
                    [center_x - w_text/2 - 5, center_y - h_text/2 - 5, center_x + w_text/2 + 5, center_y + h_text/2 + 5],
                    fill="white", outline="red"
                )
                draw.text((center_x - w_text/2, center_y - h_text/2), text, fill="red", font=font)
                
                grid_map[count] = (center_x, center_y)
                count += 1
                
        return image, grid_map
