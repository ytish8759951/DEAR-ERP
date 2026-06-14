def analyze_product_image(image_path=None):
    size_chart = "\n".join(
        [
            "尺寸：F",
            "肩寬：50",
            "胸圍：55",
            "袖長：22",
            "衣長：62",
        ]
    )

    product_name = "韓系寬鬆顯瘦短袖上衣"
    ai_description = "韓系寬鬆版型設計，修飾身形不挑身材，柔軟舒適布料，日常穿搭輕鬆有型。"
    line_group_text = "\n".join(
        [
            f"【{product_name}】",
            "",
            "顏色：",
            "白色、黑色、灰色",
            "",
            "尺寸：",
            "F",
            "",
            "售價：",
            "$590",
            "",
            "尺寸表：",
            size_chart,
            "",
            "商品特色：",
            "韓系寬鬆版型",
            "修飾身形不挑人",
            "日常百搭好穿",
            "單穿或內搭都適合",
        ]
    )
    live_script = "這件版型真的超修飾，穿起來不貼身，單穿好看，搭牛仔褲或短裙都很適合。"

    return {
        "product_name": product_name,
        "size_chart": size_chart,
        "ai_description": ai_description,
        "line_group_text": line_group_text,
        "live_script": live_script,
    }
