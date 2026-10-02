import segno


class SegnoQrRenderer:
    def svg_data_uri(self, content: str, *, scale: int) -> str:
        return str(segno.make(content, error="m").svg_data_uri(scale=scale, border=2))
