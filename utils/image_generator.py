# utils/image_generator.py

import io
from PIL import Image, ImageDraw, ImageFont
import logging


# Define layout constants to avoid magic numbers in drawing code
# These can be tuned easily if you change the background image
class LayoutConfig:
    BACKGROUND_SIZE = (1366, 757)
    RANK_IMAGE_SIZE = (55, 55)
    UNRANKED_ICON_SIZE = (40, 40)

    # Font sizes
    FONT_SIZE_NORMAL = 25
    FONT_SIZE_MEDIUM = 23
    FONT_SIZE_SMALL = 21

    # Base coordinates for the top-left of each column
    COLUMN_X_OFFSETS = [70, 513, 956]

    # Y-offsets for each row within a column
    ROW_Y_OFFSETS = [0, 73, 146, 219, 292, 364, 439]

    # Relative offsets for elements within each player slot
    # (from the top-left corner of the slot)
    NAME_OFFSET = (45, 235)
    RANK_ICON_OFFSET = (165, 225)  # Default Y, will be adjusted
    RANK_TEXT_OFFSET = (237, 235)


class ImageGenerator:
    """Handles the creation of the leaderboard image."""

    def __init__(self, font_path: str):
        """
        Initializes the ImageGenerator by loading fonts.
        This is done once to improve performance.
        """
        try:
            self.layout = LayoutConfig()
            self.font_normal = ImageFont.truetype(font_path, self.layout.FONT_SIZE_NORMAL)
            self.font_medium = ImageFont.truetype(font_path, self.layout.FONT_SIZE_MEDIUM)
            self.font_small = ImageFont.truetype(font_path, self.layout.FONT_SIZE_SMALL)
        except IOError:
            logging.error(f"Could not load font from path: {font_path}. Please ensure the font file exists.")
            raise

    def _get_player_font(self, player_name: str) -> ImageFont.FreeTypeFont:
        """Selects the appropriate font size based on the player name's length."""
        if len(player_name) > 12:
            return self.font_small
        return self.font_normal

    def _draw_player(self, draw: ImageDraw.Draw, image: Image.Image, player_data: tuple, base_x: int, base_y: int):
        summoner_name, _, _, tier, tier_division_lp = player_data

        # Draw Summoner Name
        name_font = self._get_player_font(summoner_name)
        name_pos = (base_x + self.layout.NAME_OFFSET[0], base_y + self.layout.NAME_OFFSET[1])
        draw.text(name_pos, summoner_name, fill="white", font=name_font)

        # Draw Rank Icon
        icon_path = f"assets/img/{tier.upper()}.png"  # Initialize before try
        try:
            with Image.open(icon_path).convert("RGBA") as rank_icon:
                is_unranked = tier.upper() == "UNRANKED"
                icon_size = self.layout.UNRANKED_ICON_SIZE if is_unranked else self.layout.RANK_IMAGE_SIZE
                rank_icon.thumbnail(icon_size)

                icon_x = base_x + self.layout.RANK_ICON_OFFSET[0]
                icon_y_base = base_y + self.layout.RANK_ICON_OFFSET[1]
                icon_y = icon_y_base - 5 if not is_unranked and tier.upper() not in [
                    "PLATINUM", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"
                ] else icon_y_base

                image.alpha_composite(rank_icon, dest=(icon_x, icon_y))
        except FileNotFoundError:
            logging.warning(f"Rank icon not found: {icon_path}")
        except Exception as e:
            logging.error(f"Failed to process rank icon {icon_path}: {e}")

        # Draw Rank Text
        rank_font = self.font_medium if tier.upper() in ["GRANDMASTER", "CHALLENGER"] else self.font_normal
        rank_text_pos = (base_x + self.layout.RANK_TEXT_OFFSET[0], base_y + self.layout.RANK_TEXT_OFFSET[1])
        draw.text(rank_text_pos, tier_division_lp, fill="white", font=rank_font)

    def generate_leaderboard_image(self, rankings: list, background_path: str) -> io.BytesIO | None:
        """
        Creates the full leaderboard image with all players and returns it as a BytesIO object.
        """
        try:
            with Image.open(background_path).convert("RGBA") as background:
                background = background.resize(self.layout.BACKGROUND_SIZE)

                # Create a new image to draw on
                image = Image.new("RGBA", self.layout.BACKGROUND_SIZE)
                image.paste(background)

                draw = ImageDraw.Draw(image)

                # Loop through columns and rows to place each player
                for i, col_x in enumerate(self.layout.COLUMN_X_OFFSETS):
                    for j, row_y in enumerate(self.layout.ROW_Y_OFFSETS):
                        player_index = i * len(self.layout.ROW_Y_OFFSETS) + j
                        if player_index >= len(rankings):
                            break

                        player = rankings[player_index]
                        self._draw_player(draw, image, player, col_x, row_y)

                # Save the final image to an in-memory buffer
                final_buffer = io.BytesIO()
                image.save(final_buffer, format="PNG")
                final_buffer.seek(0)
                return final_buffer

        except FileNotFoundError:
            logging.error(f"Background image not found at: {background_path}")
            return None
        except Exception as e:
            logging.error(f"An error occurred during image generation: {e}")
            return None