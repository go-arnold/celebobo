import segno


class SvgQrCode:
    """A QR code as an SVG data URI, which WeasyPrint draws as is in the PDF."""

    def data_uri(self, content: str) -> str:
        return str(segno.make(content, error="m").svg_data_uri(scale=3, border=2))
