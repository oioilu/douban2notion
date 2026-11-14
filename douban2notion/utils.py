import calendar
from datetime import datetime
from datetime import timedelta
import hashlib
import os
import re
import time
import requests
import base64
from douban2notion.config import (
    RICH_TEXT,
    URL,
    RELATION,
    NUMBER,
    DATE,
    FILES,
    STATUS,
    TITLE,
    SELECT,
    MULTI_SELECT
)
import pendulum

MAX_LENGTH = (
    1024  # NOTION 2000个字符限制https://developers.notion.com/reference/request-limits
)

tz = "Asia/Shanghai"
def get_heading(level, content):
    if level == 1:
        heading = "heading_1"
    elif level == 2:
        heading = "heading_2"
    else:
        heading = "heading_3"
    return {
        "type": heading,
        heading: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": content[:MAX_LENGTH],
                    },
                }
            ],
            "color": "default",
            "is_toggleable": False,
        },
    }


def get_table_of_contents():
    """获取目录"""
    return {"type": "table_of_contents", "table_of_contents": {"color": "default"}}


def get_title(content):
    return {"title": [{"type": "text", "text": {"content": content[:MAX_LENGTH]}}]}


def get_rich_text(content):
    return {"rich_text": [{"type": "text", "text": {"content": content[:MAX_LENGTH]}}]}


def get_url(url):
    return {"url": url}


def get_file(url):
    return {"files": [{"type": "external", "name": "Cover", "external": {"url": url}}]}


def get_multi_select(names):
    return {"multi_select": [{"name": name} for name in names]}


def get_relation(ids):
    return {"relation": [{"id": id} for id in ids]}


def get_date(start, end=None):
    return {
        "date": {
            "start": start,
            "end": end,
            "time_zone": "Asia/Shanghai",
        }
    }


def get_icon(url):
    return {"type": "external", "external": {"url": url}}


def get_select(name):
    return {"select": {"name": name}}


def get_number(number):
    return {"number": number}


def get_quote(content):
    return {
        "type": "quote",
        "quote": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": content[:MAX_LENGTH]},
                }
            ],
            "color": "default",
        },
    }


def get_callout(content, style, colorStyle, reviewId):
    # 根据不同的划线样式设置不同的emoji 直线type=0 背景颜色是1 波浪线是2
    emoji = "〰️"
    if style == 0:
        emoji = "💡"
    elif style == 1:
        emoji = "⭐"
    # 如果reviewId不是空说明是笔记
    if reviewId != None:
        emoji = "✍️"
    color = "default"
    # 根据划线颜色设置文字的颜色
    if colorStyle == 1:
        color = "red"
    elif colorStyle == 2:
        color = "purple"
    elif colorStyle == 3:
        color = "blue"
    elif colorStyle == 4:
        color = "green"
    elif colorStyle == 5:
        color = "yellow"
    return {
        "type": "callout",
        "callout": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": content[:MAX_LENGTH],
                    },
                }
            ],
            "icon": {"emoji": emoji},
            "color": color,
        },
    }


def get_rich_text_from_result(result, name):
    return result.get("properties").get(name).get("rich_text")[0].get("plain_text")


def get_number_from_result(result, name):
    return result.get("properties").get(name).get("number")


def format_time(time):
    """将秒格式化为 xx时xx分格式"""
    result = ""
    hour = time // 3600
    if hour > 0:
        result += f"{hour}时"
    minutes = time % 3600 // 60
    if minutes > 0:
        result += f"{minutes}分"
    return result


def format_date(date, format="%Y-%m-%d %H:%M:%S"):
    return date.strftime(format)


def timestamp_to_date(timestamp):
    """时间戳转化为date"""
    return datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)


def get_first_and_last_day_of_month(date):
    # 获取给定日期所在月的第一天
    first_day = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 获取给定日期所在月的最后一天
    _, last_day_of_month = calendar.monthrange(date.year, date.month)
    last_day = date.replace(
        day=last_day_of_month, hour=0, minute=0, second=0, microsecond=0
    )

    return first_day, last_day


def get_first_and_last_day_of_year(date):
    # 获取给定日期所在年的第一天
    first_day = date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # 获取给定日期所在年的最后一天
    last_day = date.replace(month=12, day=31, hour=0, minute=0, second=0, microsecond=0)

    return first_day, last_day


def get_first_and_last_day_of_week(date):
    # 获取给定日期所在周的第一天（星期一）
    first_day_of_week = (date - timedelta(days=date.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # 获取给定日期所在周的最后一天（星期日）
    last_day_of_week = first_day_of_week + timedelta(days=6)

    return first_day_of_week, last_day_of_week


NOTION_API_BASE = "https://api.notion.com/v1"
# 豆瓣图床有防盗链：不带 Referer 一律 418。按站点依次尝试。
DOUBAN_REFERERS = ("https://movie.douban.com/", "https://book.douban.com/", "")
IMAGE_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_IMAGE_UPLOAD_CACHE = {}


def _fetch_image_with_referer(url):
    """带 Referer 下载豆瓣图片，返回 (bytes, content_type)；失败返回 (None, None)。"""
    for referer in DOUBAN_REFERERS:
        headers = {"User-Agent": IMAGE_UA}
        if referer:
            headers["Referer"] = referer
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except Exception as exc:
            print(f"封面下载异常 {url}: {exc}")
            continue
        if resp.ok and resp.content:
            return resp.content, (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0]
    return None, None


def upload_image_to_notion(url, retries=3):
    """把外链封面下载后上传进 Notion，返回 file_upload id；失败返回 None。

    为什么不能直接把豆瓣外链给 Notion：Notion 的服务端下载不带 Referer，豆瓣返回 418。
    """
    if not url:
        return None
    if url in _IMAGE_UPLOAD_CACHE:
        return _IMAGE_UPLOAD_CACHE[url]
    # 电影页用的是 MOVIE_NOTION_TOKEN，书籍页用 BOOK_NOTION_TOKEN；按同样顺序兜底
    token = (os.getenv("NOTION_TOKEN") or os.getenv("MOVIE_NOTION_TOKEN")
             or os.getenv("BOOK_NOTION_TOKEN"))
    if not token:
        print("没有可用的 Notion 令牌，封面只能保留外链")
        return None
    content, content_type = _fetch_image_with_referer(url)
    if not content:
        print(f"封面取不到（疑似防盗链拦截）：{url}")
        return None
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(content_type, "jpg")
    filename = f"cover.{ext}"
    auth = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"}
    for _ in range(retries):
        try:
            created = requests.post(
                f"{NOTION_API_BASE}/file_uploads",
                headers={**auth, "Content-Type": "application/json"},
                json={"filename": filename, "content_type": content_type},
                timeout=30,
            )
            if not created.ok:
                print(f"创建上传失败 {created.status_code} {created.text[:120]}")
                time.sleep(2)
                continue
            upload_id = created.json()["id"]
            sent = requests.post(
                f"{NOTION_API_BASE}/file_uploads/{upload_id}/send",
                headers=auth,
                files={"file": (filename, content, content_type)},
                timeout=60,
            )
            if sent.ok:
                _IMAGE_UPLOAD_CACHE[url] = upload_id
                print(f"封面已上传 {filename} {len(content)}B")
                return upload_id
            print(f"上传文件失败 {sent.status_code} {sent.text[:120]}")
        except Exception as exc:
            print(f"封面上传异常 {exc}")
        time.sleep(2)
    return None


def cover_is_uploaded(property_value):
    """判断封面是不是已经上传进 Notion 的文件（而不是外链）。"""
    files = (property_value or {}).get("files") or []
    return bool(files) and files[0].get("type") == "file"


def get_properties(dict1, dict2):
    properties = {}
    for key, value in dict1.items():
        type = dict2.get(key)
        if value == None:
            continue
        property = None
        if type == TITLE:
            property = {
                "title": [
                    {"type": "text", "text": {"content": value[:MAX_LENGTH]}}
                ]
            }
        elif type == RICH_TEXT:
            property = {
                "rich_text": [
                    {"type": "text", "text": {"content": value[:MAX_LENGTH]}}
                ]
            }
        elif type == NUMBER:
            property = {"number": value}
        elif type == STATUS:
            property = {"status": {"name": value}}
        elif type == FILES:
            upload_id = upload_image_to_notion(value)
            if upload_id:
                # name 里留原始豆瓣地址，供下次比对是否需要重新同步
                property = {"files": [{"type": "file_upload", "name": value, "file_upload": {"id": upload_id}}]}
            else:
                print(f"封面回退为外链（可能显示破损）：{value}")
                property = {"files": [{"type": "external", "name": "Cover", "external": {"url": value}}]}
        elif type == DATE:
            property = {
                "date": {
                    "start": pendulum.from_timestamp(
                        value, tz="Asia/Shanghai"
                    ).to_datetime_string(),
                    "time_zone": "Asia/Shanghai",
                }
            }
        elif type==URL:
            property = {"url": value}        
        elif type==SELECT:
            property = {"select": {"name": value}}        
        elif type==MULTI_SELECT:
            property = {"multi_select": [{"name": name} for name in value]}
        elif type == RELATION:
            property = {"relation": [{"id": id} for id in value]}
        if property:
            properties[key] = property
    return properties


def get_property_value(property):
    """从Property中获取值"""
    type = property.get("type")
    content = property.get(type)
    if content is None:
        return None
    if type == "title" or type == "rich_text":
        if(len(content)>0):
            return content[0].get("plain_text")
        else:
            return None
    elif type == "status" or type == "select":
        return content.get("name")
    elif type == "files":
        # 不考虑多文件情况
        if len(content) == 0:
            return None
        first = content[0]
        if first.get("type") == "external":
            return (first.get("external") or {}).get("url")
        # 上传进 Notion 的文件：name 存的是原始豆瓣地址
        return first.get("name")
    elif type == "date":
        return str_to_timestamp(content.get("start"))
    else:
        return content


def calculate_book_str_id(book_id):
    md5 = hashlib.md5()
    md5.update(book_id.encode("utf-8"))
    digest = md5.hexdigest()
    result = digest[0:3]
    code, transformed_ids = transform_id(book_id)
    result += code + "2" + digest[-2:]

    for i in range(len(transformed_ids)):
        hex_length_str = format(len(transformed_ids[i]), "x")
        if len(hex_length_str) == 1:
            hex_length_str = "0" + hex_length_str

        result += hex_length_str + transformed_ids[i]

        if i < len(transformed_ids) - 1:
            result += "g"

    if len(result) < 20:
        result += digest[0 : 20 - len(result)]
    md5 = hashlib.md5()
    md5.update(result.encode("utf-8"))
    result += md5.hexdigest()[0:3]
    return result

def transform_id(book_id):
    id_length = len(book_id)
    if re.match("^\d*$", book_id):
        ary = []
        for i in range(0, id_length, 9):
            ary.append(format(int(book_id[i : min(i + 9, id_length)]), "x"))
        return "3", ary

    result = ""
    for i in range(id_length):
        result += format(ord(book_id[i]), "x")
    return "4", [result]

def get_weread_url(book_id):
    return f"https://weread.qq.com/web/reader/{calculate_book_str_id(book_id)}"

def str_to_timestamp(date_str):
    if not date_str:
        return 0

    try:
        dt = pendulum.parse(date_str)
        # 获取时间戳
        return int(dt.timestamp())
    except Exception as e:
        print(f"⚠️  无法解析日期 '{date_str}': {type(e).__name__}")
        return 0

upload_url = 'https://wereadassets.malinkang.com/'


def upload_image(folder_path, filename,file_path):
    # 将文件内容编码为Base64
    with open(file_path, 'rb') as file:
        content_base64 = base64.b64encode(file.read()).decode('utf-8')

    # 构建请求的JSON数据
    data = {
        'file': content_base64,
        'filename': filename,
        'folder': folder_path
    }

    response = requests.post(upload_url, json=data)

    if response.status_code == 200:
        print('File uploaded successfully.')
        return response.text
    else:
        return None

def url_to_md5(url):
    # 创建一个md5哈希对象
    md5_hash = hashlib.md5()

    # 对URL进行编码，准备进行哈希处理
    # 默认使用utf-8编码
    encoded_url = url.encode('utf-8')

    # 更新哈希对象的状态
    md5_hash.update(encoded_url)

    # 获取十六进制的哈希表示
    hex_digest = md5_hash.hexdigest()

    return hex_digest

def download_image(url, save_dir="cover"):
    # 确保目录存在，如果不存在则创建
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    file_name = url_to_md5(url) + ".jpg"
    save_path = os.path.join(save_dir, file_name)

    # 检查文件是否已经存在，如果存在则不进行下载
    if os.path.exists(save_path):
        print(f"File {file_name} already exists. Skipping download.")
        return save_path

    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=128):
                file.write(chunk)
        print(f"Image downloaded successfully to {save_path}")
    else:
        print(f"Failed to download image. Status code: {response.status_code}")
    return save_path

def upload_cover(url):
    cover_file = download_image(url)
    return upload_image("cover",f"{cover_file.split('/')[-1]}",cover_file)

def get_embed(url):
    return {"type": "embed", "embed": {"url": url}}
