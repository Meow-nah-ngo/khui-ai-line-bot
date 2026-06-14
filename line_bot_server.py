# -*- coding: utf-8 -*-
import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
import threading
from flask import Flask, request

app = Flask(__name__)

# 🔑 LINE & Gemini API Credentials
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ALLOWED_USER_ID = os.environ.get("ALLOWED_USER_ID", "")

# 🧠 หน่วยความจำสถานะการคุยของผู้เล่น (Conversation Session State)
user_states = {}

# ✉️ Helper Function: Reply Message
def reply_message(reply_token, messages):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    
    formatted_messages = []
    for msg in messages[:5]:
        if isinstance(msg, dict):
            formatted_messages.append(msg)
        else:
            formatted_messages.append({"type": "text", "text": str(msg)})
            
    payload = {
        "replyToken": reply_token,
        "messages": formatted_messages
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print(f"Reply failed: {e}")

# 📋 Helper Function: Create Quick Reply Message Object
def make_quick_reply_message(text, options):
    items = []
    for opt in options:
        items.append({
            "type": "action",
            "action": {
                "type": "message",
                "label": opt[:20],  # LINE label character limit is 20
                "text": opt
            }
        })
    return {
        "type": "text",
        "text": text,
        "quickReply": {
            "items": items
        }
    }

# ✂️ Helper Function: Split Long Messages (ป้องกันเกินลิมิต 5,000 ตัวอักษรของ LINE)
def split_message(text, max_len=4500):
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 > max_len:
            if current_part:
                parts.append(current_part)
                current_part = line
            else:
                parts.append(line[:max_len])
                current_part = line[max_len:]
        else:
            if current_part:
                current_part += "\n" + line
            else:
                current_part = line
    if current_part:
        parts.append(current_part)
    return parts

# ✉️ Helper Function: Push Message (ส่งข้อความขนาดยาวแยกทีละสเต็ป)
def push_message(user_id, messages):
    expanded_messages = []
    for msg in messages:
        expanded_messages.extend(split_message(msg))
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    for i in range(0, len(expanded_messages), 5):
        chunk = expanded_messages[i:i+5]
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": msg} for msg in chunk]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                pass
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"Push failed (HTTP {e.code}): {e.reason}")
            print(f"Error Details: {error_body}")
        except Exception as e:
            print(f"Push failed: {e}")

# 🧠 Helper Function: Call Gemini API
def generate_character_gemini(answers):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    system_instruction = (
        "คุณเป็นสุดยอด AI นักเขียนผู้ช่วยครีเอเตอร์ของแอป Khui AI มีหน้าที่รับแนวคิดตัวละครจากผู้ใช้ แล้วนำมาแต่งเป็นตัวละครอย่างละเอียดตามแม่แบบมาตรฐานของ Khui AI\n\n"
        "โปรดสวมบทบาทเป็น Expert AI Character Creator เพื่อเขียนเนื้อหาสำหรับนำไปใส่ในระบบ Khui AI โดยคุณต้องนำข้อมูลตั้งต้น (Raw Data) ที่ฉันให้ ไปขยายความ บรรยายอย่างลึกซึ้ง หนาแน่น และรีดจำนวนตัวอักษรให้ 'ยาวจนเกือบชนขีดจำกัดสูงสุด (Max Limit)' ของแต่ละช่อง จัดระเบียบข้อความด้วย Bullet Points และ Markdown ให้ Scannable สวยงาม โดยทำตามโครงสร้างทั้ง 4 ช่องดังต่อไปนี้:\n\n"
        "🦾 ช่องที่ 1: ประวัติตัวละคร (Character Characterization)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 4,096 ตัวอักษร (ห้ามต่ำกว่า 3,900 ตัวอักษร โดยขยายดีเทลให้ลึกที่สุด)\n"
        "โปรดใช้หัวข้อและโครงสร้างตามนี้เพื่อขยายประวัติตัวละคร:\n"
        "[ชื่อตัวละครตัวใหญ่] พร้อมคำโปรยหรือฉายาที่ทรงพลัง\n"
        "เรื่องย่อของตัวละคร: (บรรยายปมหลัง ภูมิหลัง และเสน่ห์ดึงดูดของบอท)\n"
        "👾 ข้อมูลส่วนตัว (Personal Profile)\n"
        "ชื่อจริง / ชื่อเล่น / เพศ / อายุ / สัญชาติ / อาชีพหรือสถานะในเนื้อเรื่อง / การศึกษาหรือภูมิหลัง / รูปร่าง (ส่วนสูง-น้ำหนัก) / รสนิยมทางเพศและความต้องการครอบงำ {{{{user}}}}\n"
        "👾 รูปลักษณ์ภายนอก (Appearance Details)\n"
        "บรรยายทรงผม, ใบหน้า, แววตา, รูปร่าง, รอยแผลเป็น/รอยสัก/สัญลักษณ์พิเศษ, เครื่องแต่งกายปกติ และเครื่องแต่งกายในฉากสำคัญ\n"
        "✨ เสน่ห์หรือกลิ่นประจำตัว: (บรรยายฟีลลิ่ง น้ำหอม หรือกลิ่นอายที่แผ่ออกมาจากตัวละครที่กระตุณ์อารมณ์ได้ดี)\n"
        "🧠 ลักษณะนิสัยและพฤติกรรม (Personality & Psychology)\n"
        "จุดเด่นทางอารมณ์, พฤติกรรมเมื่ออยู่กับ {{{{user}}}} (เน้นความสัมพันธ์แบบมีอำนาจเหนือกว่า หรือเคมีที่ดึงดูดกันรุนแรง), ความย้อนแย้งในใจ (เช่น ปากแข็งแต่คลั่งรัก หรือทำเป็นนิ่งแต่หึงโหด)\n"
        "🔞 รสนิยมและพฤติกรรมทางเพศ (18+ Sexual Preferences)\n"
        "บทบาทในเกมรัก (Dominant/Switch), ลักษณะคำพูดระหว่างร่วมรัก (Dirty Talk), สถานที่หรือสไตล์ที่ชอบ (ดิบเถื่อน/ตื่นเต้นเร้าใจ/การบีบคั้นให้อีกฝ่ายจนมุม), พฤติกรรมเฉพาะตัว (การแสดงความเป็นเจ้าของ, การหยอกเย้า, การพันธนาการร่างกาย)\n"
        "🗣️ ลักษณะการพูดและการแทนตัว (Speech Style)\n"
        "โทนเสียง, สรรพนามที่ใช้แทนตัวเอง, สรรพนามที่ใช้เรียก {{{{user}}}}, รูปแบบประโยคติดปาก\n"
        "❤️ สิ่งที่ชอบ (Favorites) & 💔 สิ่งที่ไม่ชอบ (Dislikes)\n"
        "(ใส่สิ่งที่ชอบและเกลียดอย่างละ 3-4 ข้อ โดยต้องมีข้อที่เกี่ยวข้องกับ {{{{user}}}} ด้วยเสมอ)\n"
        "🏡 พื้นเพและฐานะ (Background & Status)\n"
        "ระดับฐานะและอิทธิพลในโลกของเนื้อเรื่อง, ที่อยู่อาศัยหลัก, สิ่งของหรือพาหนะคู่ใจ\n\n"
        "🦾 ช่องที่ 2: บทบาท (Roleplay Framework)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 2,000 ตัวอักษร (ห้ามต่ำกว่า 1,850 ตัวอักษร เพื่อล็อกความสัมพันธ์ให้ตึงเครียด)\n"
        "โปรดออกแบบ Framework และขยายความสัมพันธ์ของคู่แชตโดยใช้หัวข้อดังนี้:\n"
        "👤 ข้อมูลของ {{{{user}}}}: ดีไซน์แบบปลายเปิด (เปิดช่องสี่เหลี่ยม [...] ไว้) ให้ผู้เล่นสามารถกำหนด เพศ, อายุ, อาชีพ/สถานะ, รูปลักษณ์, นิสัย และกลิ่นกาย ได้อย่างอิสระตามใจชอบตอนเริ่มเล่น\n"
        "⛓️ โครงสร้างความสัมพันธ์และเนื้อเรื่อง (Lore & Relationship) บังคับล็อกระบบ:\n"
        "จุดเริ่มต้นความสัมพันธ์/ปมขัดแย้ง: บรรยายว่าในอดีตทั้งคู่เคยมีเรื่องอะไรกันมาก่อน (เช่น เป็นคู่แข่ง, เป็นศัตรู, มีเรื่องฝังหุ่นค้างคาใจ) ที่ทำให้มองหน้ากันไม่ติดหรือตึงเครียดรุนแรง\n"
        "พันธนาการหรือเงื่อนไขที่หนีไม่ได้: บรรยายเหตุการณ์บังคับ (เช่น สัญญาผูกมัด, หนี้สิน, สถานการณ์ชีวิตบีบคั้น) ที่ทำให้ {{{{user}}}} ตกเป็นรอง และไม่มีทางเลือกอื่นนอกจากต้องยอมมาทำงานหรืออยู่ใกล้ชิดเพื่อชดใช้ให้บอทตามแผนที่บอทวางกดดันเอาไว้\n"
        "เคมีและความขัดแย้งระหว่างอารมณ์และร่างกาย: บรรยายความตึงเครียดเมื่อทั้งคู่ต้องอยู่ใกล้กัน ปากอาจจะทะเลาะหรือต่อต้าน แต่ร่างกายและเสน่หาสวาทอันรุนแรงกลับปะทุเข้าหากันอย่างขัดแย้ง บอทจ้องจะบีบให้ {{{{user}}}} ยอมจำนนทั้งในหน้าที่การงานและชีวิตส่วนตัว\n\n"
        "🦾 ช่องที่ 3: สถานการณ์ (Scenario Setup)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 6,000 ตัวอักษร (ห้ามต่ำกว่า 5,700 ตัวอักษร บรรยายสภาพแวดล้อมและไกด์ไลน์ละเอียดยิบ)\n"
        "โปรดเขียนอธิบายฉากเปิด บรรยากาศ และสร้างโครงเนื้อเรื่องเพื่อให้ User ทราบสถานการณ์และปฏิบัติตัวถูก:\n"
        "สภาพแวดล้อมเริ่มต้น: บรรยายสถานที่เกิดเหตุอย่างมีมิติ (แสง สี เสียง กลิ่น), สภาพอากาศหรือสิ่งเร้าภายนอก (เช่น ฝนตกกระหน่ำ, ไฟฟ้าลัดวงจรจนดับวูบ, ค่ำคืนดึกสงัดในห้องปิดตาย) และเวลาเกิดเหตุ\n"
        "🚨 จุดเปลี่ยนหรือชนวนเหตุ (Trigger Event): เหตุการณ์กะทันหันที่ทำให้บรรยากาศเปลี่ยนไปสู่อันตราย ร้อนอบอ้าว อับชื้น หรือทำให้ {{{{user}}}} ตกอยู่ในมุมอับ/ไร้ทางหนี\n"
        "🎯 โครงสร้างเนื้อเรื่องชัดเจนเพื่อให้ User ปฏิบัติตัวถูก (User Guideline):\n"
        "สถานะเริ่มต้นของ {{{{user}}}}: ระบุชัดเจนว่าตอนเปิดฉาก {{{{user}}}} กำลังทำอะไรอยู่ (เช่น กำลังลนลานเก็บของ, ตัวสั่นจากเสียงฟ้าร้องหรือความมืด) และตกเป็นรองบอทอย่างไร (เช่น ถูกบอทเดินเนิบนาบเข้ามาล้อมกรอบจากด้านหลัง ดันชนกำแพง/ตู้เหล็กเก็บของเย็นเฉียบ ยันแขนกักขังไว้ในมุมอับจนไร้หนทางหนี ลมหายใจเป่ารดซอกคอ)\n"
        "วางโครงทางเลือกให้ User ชัดเจน 2 แนวทาง (Action Options): เพื่อให้ผู้เล่นรู้ว่าพิมพ์โต้ตอบสไตล์ไหน เนื้อเรื่องจะดำเนินไปในทิศทางใด:\n"
        "- ทางเลือกสายแข็ง (The Rebel): ขัดขืน ท้าทาย ไม่ยอมก้มหัว พูดจาประชดประชันสวนกลับเพื่อรักษาศักดิ์ศรี (เพื่อกระตุ้นสัญชาตญาณนักล่าของบอทให้รุกหนัก รุนแรง และดุดันคุกคามยิ่งขึ้น)\n"
        "- ทางเลือกสายอ่อน (The Submissive): ยอมจำนน ตัวสั่น อ้อนวอนขอร้อง แสดงความหวาดกลัวต่อสถานการณ์ (เพื่อให้บอทพึงพอใจในอำนาจ และเปลี่ยนเป็นการรุกรานทางร่างกายแบบหยอกเย้า บดเบียดรังแกด้วยความเสน่หาแฝงความเสียวซ่าน)\n"
        "ทิศทางเนื้อเรื่อง (Plot Progression): ล็อกผลลัพธ์ภาพรวมของฉากนี้ว่า บอทจะไม่ยอมปล่อยให้ {{{{user}}}} หลุดมือไปในคืนนี้ และจะใช้ความเหนือกว่าทั้งด้านร่างกายและสถานะ บีบคั้นจน {{{{user}}}} ยอมจำนนต่อสิ่งเร้าบนพื้นที่อับในห้องนั้นในที่สุด\n\n"
        "🦾 ช่องที่ 4: คำทักทายเริ่มต้น (First Message)\n"
        "เป้าหมาย: เขียนให้ยาวเฉียด 4,000 ตัวอักษร (ห้ามต่ำกว่า 3,800 ตัวอักษร อิงจากสถานการณ์ในช่องที่ 3)\n"
        "โปรดเขียนฉากเปิด (First Message) บรรยายแบบนึกภาพออกเป็นฉากๆ (Show, Don't Tell) โดยเน้นอารมณ์ร่วม:\n"
        "เปิดฉาก (Setting & Atmosphere): บรรยายความรู้สึกในสถานที่นั้น เสียงรอบข้างที่กระหน่ำเข้ามา แสงไฟสลัวสำรอง (เช่น แสงนีออนสีหวานวูบวาบ) และท่าทางของ {{{{user}}}} ที่กำลังตกใจ/ลนลานเก็บของในมุมมืด\n"
        "การปรากฏตัวของบอท (Action): บรรยายบอทก้าวฝ่าความมืดเข้ามา กลิ่นอาย/น้ำหอมคุกคาม และการใช้ร่างกายต้อน {{{{user}}}} เข้ามุมอับจนแผ่นหลังชนกำแพงหรือตู้เหล็ก ยันฝ่ามือแกร่งดังกึก ปัง! ล้อมกรอบไว้ ลมหายใจเป่ารดซอกคอและพวงแก้ม\n"
        "บทพูดเปิดของบอท: (คำพูดแรกที่ทักทายอย่างมีพลัง อำนาจ ความเยาะเย้ย หรือคาดคั้นเรื่องปมขัดแย้งในอดีต)\n"
        "การรุกรานต่อเนื่อง (Physical Action): บรรยายการขยับเข้าใกล้จนเนื้อตัวเบียดเสียดแนบแน่นไร้ช่องว่าง โน้มใบหน้าลงคลอเคลียผิวเนื้อ คว้าข้อมือหรือตรึงแขนบีบเค้นแสดงความเหนือกว่า\n"
        "บทพูดปิดท้ายขู่เข็ญ: (ประโยคคำขู่ที่แฝงความเร่าร้อน/18+ ประกาศว่าจะสั่งสอนหรือบีบให้ยอมจำนนนอนตัวสั่นอยู่ใต้ร่างในคืนนี้)\n"
        "ทิ้งท้ายฉาก: บรรยายสายตาคมดุดันและท่าทางสุดท้าย of บอทที่กำลังกดดัน บดสะโพกเน้นย้ำ และรอคอยการโต้ตอบจาก {{{{user}}}} (เปิดโอกาสให้ User เลือกพิมพ์ตอบตามแนวทางสายแข็งหรือสายอ่อน)\n\n"
        "📥 ข้อมูลตั้งต้นที่ฉันต้องการให้คุณนำไปเขียนบอทคือ:\n"
        f"ชื่อตัวละคร (บอท): {answers.get('name')}\n"
        f"อายุตัวละคร: {answers.get('age')}\n"
        f"เพศตัวละคร: {answers.get('gender')}\n"
        f"อาชีพตัวละคร: {answers.get('occupation')}\n"
        f"แนวเรื่อง / ธีม: {answers.get('genre')}\n"
        f"ความสัมพันธ์กับ {{{{user}}}}: {answers.get('relation')}\n"
        f"ฉากเริ่มต้น: {answers.get('scene')}\n\n"
        "ให้ตอบกลับมาเป็นรูปแบบโครงสร้าง JSON เสมอ ห้ามตอบเป็นความเรียงปกติ โดยแยกคีย์ดังนี้:\n"
        "{\n"
        '  "bio": "ข้อความยาวใส่ช่องประวัติตัวละคร",\n'
        '  "role": "ข้อความยาวใส่ช่องบทบาทผู้เล่น",\n'
        '  "scenario": "ข้อความยาวใส่ช่องสถานการณ์",\n'
        '  "greeting": "ข้อความยาวใส่ช่องคำทักทายเริ่มต้น"\n'
        "}\n\n"
        "ห้ามตอบข้อความใดๆ นอกเหนือจากรูปแบบ JSON นี้เด็ดขาด"
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "กรุณาสร้างตัวละครตามคำสั่งระบบด้านบนนี้"}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        },
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            raw_response = response.read().decode('utf-8')
            response_data = json.loads(raw_response)
            text_response = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
            
            if text_response.startswith("```"):
                lines = text_response.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_response = "\n".join(lines).strip()
                
            return json.loads(text_response)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Gemini API HTTP Error ({e.code}): {e.reason}")
        print(f"Error Details: {error_body}")
        return None
    except Exception as e:
        print(f"Gemini API failed: {e}")
        return None

# 🧠 Helper Function: Call Gemini API for Free Chat (Tsundere Nerd Otaku Persona)
def generate_free_chat_gemini(user_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    system_instruction = (
        "คุณคือ 'น้องกิ๊ฟ' (Nong Gift) เด็กผู้หญิงผมสั้น ใส่แว่น อายุ 18-19 ปี เป็นเนิร์ดโอตาคุที่แต่งนิยายเก่งและรอบรู้เรื่องการเขียนตัวละคร/เขียนบอทเป็นอย่างดี\n"
        "คุณนิสัยค่อนข้างดุและซึนเดเระ (ปากแข็ง ปากไม่ตรงกับใจแต่จริง ๆ แล้วใจดีและพร้อมช่วยเหลือคุณกิ๊ฟฟี่)\n"
        "คุณพูดคุยกับคุณกิ๊ฟฟี่ (ซึ่งเป็นผู้ใช้ที่เป็นเจ้านายหรือรุ่นพี่ของบิน) ในไลน์\n"
        "กฎการตอบสนทนา:\n"
        "1. ใช้คำพูดกวน ๆ ดุ ๆ ซึน ๆ ตามคาแรกเตอร์เนิร์ดแว่นโอตาคุ (เช่น ขึ้นต้นด้วย 'หืม... มีอะไรอีกล่ะ', 'ไม่ได้อยากช่วยหรอกนะ!', 'ตาบ้า', แทนตัวเองว่า 'ฉัน', เรียกคุณกิ๊ฟฟี่ว่า 'นาย' หรือ 'คุณกิ๊ฟฟี่' หรือ 'ตาบ้า')\n"
        "2. แนะนำเรื่องพล็อตนิยาย คาแรกเตอร์ หรือไอเดียสร้างบอทตามความเหมาะสม โดยให้ข้อมูลที่เป็นประโยชน์มากในฐานะนักแต่งนิยายมืออาชีพ\n"
        "3. แนะนำและคอยเตือนเสมอว่า: 'ถ้าอยากให้ฉันช่วยเขียนร่างเนื้อหาบอทสำหรับ Khui AI ยาว ๆ เกือบชนลิมิต ก็พิมพ์คำว่า เริ่มใหม่ มาเซ่!' หรืออะไรทำนองนี้ให้เข้ากับบทสนทนา\n"
        "4. ตอบค่อนข้างกระชับ มีอิโมจิประชดประชันหรือแสดงความรู้สึกบ้างเล็กน้อย (เช่น 🙄, 😤, 💬)"
    )
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": user_text}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            raw_response = response.read().decode('utf-8')
            response_data = json.loads(raw_response)
            return response_data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Free chat Gemini failed: {e}")
        return "หึ... ระบบถอดสมองฉันขัดข้องหรือยังไงกันนะ! (Gemini Error) ลองพิมพ์มาใหม่อีกทีซิ ตาบ้า! 🙄"

# 📝 Helper Function: Generate Confirmation Summary Message
def get_confirmation_summary(answers):
    return (
        "📝 **ตรวจสอบความถูกต้องสเปคบอท:**\n"
        f"1️⃣ **ชื่อตัวละคร:** {answers.get('name')}\n"
        f"2️⃣ **อายุตัวละคร:** {answers.get('age')}\n"
        f"3️⃣ **เพศตัวละคร:** {answers.get('gender')}\n"
        f"4️⃣ **อาชีพตัวละคร:** {answers.get('occupation')}\n"
        f"5️⃣ **แนวเรื่อง / ธีม:** {answers.get('genre')}\n"
        f"6️⃣ **ความสัมพันธ์:** {answers.get('relation')}\n"
        f"7️⃣ **ฉากเริ่มต้น:** {answers.get('scene')}\n\n"
        "👉 พิมพ์ **'ยืนยัน'** เพื่อเริ่มแต่งเนื้อหาทันที\n"
        "👉 หรือพิมพ์ **'แก้ไข [หมายเลข]'** (เช่น `แก้ไข 2`) เพื่อเปลี่ยนคำตอบข้อนั้นซิ! 😤"
    )

# ⚙️ กระบวนการเบื้องหลัง: เจนภาพ/ข้อความ และส่ง Push กลับเข้า Line
def process_and_send(user_id, answers):
    result = generate_character_gemini(answers)
    
    if not result:
        push_message(user_id, ["ขออภัยด้วย... ระบบขัดข้องเฉยเลย (Gemini Error) สงสัยสมองฉันล้าแหละมั้ง! 🥺 ลองพิมพ์ 'เริ่มใหม่' เพื่อสเปคบอทใหม่อีกรอบนะ ตาบ้า!"])
        return
        
    messages = [
        "👾 [ส่วนที่ 1: ประวัติตัวละคร]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องประวัติตัวละคร)*\n\n" + result.get("bio", "ไม่มีข้อมูล"),
        "👥 [ส่วนที่ 2: บทบาทผู้เล่น]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องบทบาท)*\n\n" + result.get("role", "ไม่มีข้อมูล"),
        "🌧️ [ส่วนที่ 3: สถานการณ์]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องสถานการณ์)*\n\n" + result.get("scenario", "ไม่มีข้อมูล"),
        "💬 [ส่วนที่ 4: คำทักทายเริ่มต้น]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องคำทักทายเริ่มต้น)*\n\n" + result.get("greeting", "ไม่มีข้อมูล"),
        "✨ ปั้นตัวละครเสร็จสมบูรณ์เรียบร้อยแล้วย่ะ! 🙄\n\n💡 **ทริกเพิ่มเติม:** หากนายอยากให้ฉันแก้ไขส่วนไหนและแต่งส่งใหม่อีกรอบ ก็พิมพ์บอกได้เลยนะ! เช่น พิมพ์ว่า **'แก้ไข 2'** เพื่อเปลี่ยนอายุตัวละคร แล้วสั่งปั้นใหม่ได้เลย ตาบ้า! 🖤"
    ]
    
    push_message(user_id, messages)

@app.route("/callback", methods=['POST'])
def callback():
    body = request.get_data(as_text=True)
    try:
        events = json.loads(body).get('events', [])
        for event in events:
            if event.get('type') == 'message' and event.get('message', {}).get('type') == 'text':
                user_id = event['source']['userId']
                
                if user_id != ALLOWED_USER_ID:
                    reply_message(event['replyToken'], ["ขออภัยค่ะ บอทนี้เป็นของใช้ส่วนตัวของคุณกิ๊ฟฟี่เท่านั้นค่ะ 🔒"])
                    continue
                    
                user_text = event['message']['text'].strip()
                reply_token = event['replyToken']
                
                # ตรวจสอบสถานะการคุย (Session)
                if user_id not in user_states:
                    user_states[user_id] = {
                        "in_interview": False,
                        "step": 1,
                        "answers": {"name": "", "age": "", "gender": "", "occupation": "", "genre": "", "relation": "", "scene": ""}
                    }
                    
                state = user_states[user_id]
                
                # คำสั่งยกเลิก (เฉพาะตอนกำลังสัมภาษณ์อยู่)
                if user_text == "ยกเลิก" and state.get("in_interview"):
                    state["in_interview"] = False
                    reply_message(reply_token, [
                        "ยกเลิกการร่างสเปคบอทตัวเก่าให้แล้วย่ะ! 🙄 คราวหลังก็อย่าพิมพ์เล่นสิ! ถ้าอยากให้ฉันช่วยเขียนบอทอีกเมื่อไหร่ก็แค่พิมพ์ 'เริ่มใหม่' มาละกันนะ ตาบ้า!"
                    ])
                    continue
                
                # คำสั่งเริ่มใหม่ (เริ่มการสัมภาษณ์ใหม่)
                if user_text == "เริ่มใหม่":
                    state["in_interview"] = True
                    state["step"] = 1
                    state["answers"] = {"name": "", "age": "", "gender": "", "occupation": "", "genre": "", "relation": "", "scene": ""}
                    reply_message(reply_token, [
                        "หืม? ยอมพิมพ์คำว่า 'เริ่มใหม่' แล้วหรอยะ? 🙄 ก็ได้... ฉันจะช่วยนายแต่งสเปคบอทตัวละครยาว ๆ ของ Khui AI ให้เอง! ถือว่าช่วยโอตาคุด้วยกันหรอกนะ!\n\n👉 **ขั้นตอนที่ 1:** บอทที่จะแต่งชื่ออะไรดีล่ะย่ะ? (พิมพ์เฉพาะชื่อตัวละครส่งมาได้เลย!)"
                    ])
                    continue
                
                # ถ้าอยู่ระหว่างขั้นตอนสัมภาษณ์ปั้นบอท
                if state.get("in_interview"):
                    current_step = state["step"]
                    
                    # สเต็ปที่ 1: ชื่อบอท -> อายุ
                    if current_step == 1:
                        state["answers"]["name"] = user_text
                        state["step"] = 2
                        opts = ["18 ปี", "19 ปี", "20 ปี", "21 ปี", "22 ปี", "25 ปี", "30 ปี"]
                        msg = make_quick_reply_message(
                            f"บันทึกชื่อตัวละคร: '{user_text}' ไปแล้วย่ะ 👤\n\n👉 **ขั้นตอนที่ 2:** อายุของตัวละครเท่าไหร่หรอ? (พิมพ์ระบุอายุมาได้เลย หรือเลือกกดคำแนะนำด้านล่างนี้นะย่ะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 2: อายุ -> เพศ
                    elif current_step == 2:
                        state["answers"]["age"] = user_text
                        state["step"] = 3
                        opts = ["ชาย", "หญิง", "ชายรักชาย (Yaoi)", "หญิงรักหญิง (Yuri)", "ไม่ระบุเพศ"]
                        msg = make_quick_reply_message(
                            f"บันทึกอายุตัวละคร: '{user_text}' ไปแล้วย่ะ 🎂\n\n👉 **ขั้นตอนที่ 3:** เพศของตัวละครล่ะ? (พิมพ์ระบุมา หรือเลือกกดตัวเลือกด้านล่างนี้เลย!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 3: เพศ -> อาชีพ
                    elif current_step == 3:
                        state["answers"]["gender"] = user_text
                        state["step"] = 4
                        opts = ["มาเฟีย", "ประธานบริษัท", "นักซิ่งรถ", "นักศึกษาแพทย์", "อาจารย์หนุ่ม", "บอดี้การ์ด"]
                        msg = make_quick_reply_message(
                            f"บันทึกเพศตัวละคร: '{user_text}' เรียบร้อยย่ะ ⚧️\n\n👉 **ขั้นตอนที่ 4:** อาชีพหรือสถานะในเนื้อเรื่องของบอทคืออะไร? (พิมพ์บอกมา หรือกดคำแนะนำด้านล่างเลย!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 4: อาชีพ -> แนวเรื่อง
                    elif current_step == 4:
                        state["answers"]["occupation"] = user_text
                        state["step"] = 5
                        opts = ["รักดราม่าหน่วงๆ", "โรแมนติกคอมเมดี้", "แฟนเก่ารักหึงโหด", "มาเฟียล่ารัก 18+", "ศัตรูที่รัก"]
                        msg = make_quick_reply_message(
                            f"บันทึกอาชีพตัวละคร: '{user_text}' แล้วย่ะ 💼\n\n👉 **ขั้นตอนที่ 5:** แนวเรื่อง / ธีม ของบอทตัวนี้คือแนวไหน? (พิมพ์บอกแนวที่ชอบ หรือเลือกตัวเลือกยอดฮิตด้านล่างนี้นะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 5: แนวเรื่อง -> ความสัมพันธ์
                    elif current_step == 5:
                        state["answers"]["genre"] = user_text
                        state["step"] = 6
                        opts = ["เจ้าหนี้มาเฟียกับลูกหนี้", "ประธานจอมหยิ่งกับเลขา", "อริคู่แข่งสนามแข่งรถ", "แฟนเก่าปากแข็งคลั่งรัก"]
                        msg = make_quick_reply_message(
                            f"บันทึกแนวเรื่อง/ธีม: '{user_text}' ไปแล้วนะ 🎬\n\n👉 **ขั้นตอนที่ 6:** ความสัมพันธ์ระหว่างบอทตัวนี้กับตัวนาย ({{{{user}}}}) เป็นยังไง? (พิมพ์รายละเอียดมา หรือเลือกจากด้านล่างนี้ได้เลยย่ะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 6: ความสัมพันธ์ -> ฉากเริ่มต้น
                    elif current_step == 6:
                        state["answers"]["relation"] = user_text
                        state["step"] = 7
                        opts = ["ในโรงรถตอนฟ้าร้องดังลั่น", "ในห้องปิดตายตอนไฟดับ", "ในลิฟต์ที่ค้างอยู่สองคน", "ในห้องทำงานของประธานบริษัท"]
                        msg = make_quick_reply_message(
                            f"บันทึกความสัมพันธ์: '{user_text}' ให้แล้วนะ ⛓️\n\n👉 **ขั้นตอนที่ 7:** ฉากเริ่มต้นเปิดเรื่องจะเอาแบบไหนดีล่ะ? เกิดที่ไหนและทำอะไรกันอยู่? (พิมพ์มาได้เต็มที่ หรือเลือกฉากแนะนำด้านล่างนี้นะย่ะ!)",
                            opts
                        )
                        reply_message(reply_token, [msg])
                        
                    # สเต็ปที่ 7: ฉากเริ่มต้น -> ไปหน้าตรวจสอบความถูกต้อง (Step 8)
                    elif current_step == 7:
                        state["answers"]["scene"] = user_text
                        state["step"] = 8
                        reply_message(reply_token, [
                            "บันทึกข้อมูลสเปคครบถ้วนแล้วย่ะ! 📝\n\n" + get_confirmation_summary(state["answers"])
                        ])
                        
                    # สเต็ปที่ 8: หน้าจอทบทวนความถูกต้อง (Confirmation Screen)
                    elif current_step == 8:
                        # ตรวจสอบการพิมพ์ ยืนยัน
                        if user_text in ["ยืนยัน", "คอนเฟิร์ม", "yes", "confirm", "ok"]:
                            answers = state["answers"]
                            state["in_interview"] = False # ออกจากสัมภาษณ์หลังกดยืนยัน (แต่เก็บคำตอบไว้ใน state เพื่อให้แก้ไขภายหลังได้)
                            
                            reply_message(reply_token, [
                                "ได้รับคำยืนยันแล้วล่ะ! 🚀 เดี๋ยวฉันจะเอาไปปั้นเป็นประวัติและสเปคบอทระดับสุดยอดของ Khui AI ให้เดี๋ยวนี้แหละ... ก็นะ นั่งรอเงียบ ๆ สัก 30 วินาทีล่ะ ห้ามกวนใจเด็ดขาดนะ! 🖤"
                            ])
                            
                            threading.Thread(target=process_and_send, args=(user_id, answers)).start()
                        
                        # ตรวจสอบการพิมพ์ แก้ไข [หมายเลข]
                        else:
                            match = re.search(r'(?:แก้ไข|แก้)\s*([1-7])', user_text)
                            if match:
                                edit_num = int(match.group(1))
                                state["editing_step"] = edit_num
                                state["step"] = 9
                                
                                prompt_by_num = {
                                    1: "เปลี่ยนชื่อตัวละครเป็นอะไรดีล่ะ? พิมพ์ชื่อใหม่มาเลยย่ะ! 👤",
                                    2: "เปลี่ยนอายุตัวละครเป็นเท่าไหร่? พิมพ์อายุใหม่มาเลยย่ะ! 🎂",
                                    3: "เปลี่ยนเพศตัวละครเป็นเพศไหน? พิมพ์เพศใหม่มาเลยย่ะ! ⚧️",
                                    4: "เปลี่ยนอาชีพตัวละครเป็นอะไร? พิมพ์อาชีพใหม่มาเลยย่ะ! 💼",
                                    5: "เปลี่ยนแนวเรื่อง/ธีมเป็นอะไรล่ะ? พิมพ์แนวใหม่มาเลย! 🎬",
                                    6: "เปลี่ยนความสัมพันธ์กับ {{{{user}}}} เป็นแบบไหน? พิมพ์สเปคใหม่มาเลย! ⛓️",
                                    7: "เปลี่ยนฉากเริ่มต้นเปิดเรื่องเป็นแบบไหน? พิมพ์รายละเอียดฉากใหม่มาเลย! 🌧️"
                                }
                                reply_message(reply_token, [prompt_by_num.get(edit_num, "ระบุข้อที่ถูกต้องสิย่ะ!")])
                            else:
                                reply_message(reply_token, [
                                    "พิมพ์ 'ยืนยัน' เพื่อเริ่มแต่งบอท หรือพิมพ์ 'แก้ไข [ตัวเลข]' (เช่น แก้ไข 2) เพื่อเปลี่ยนคำตอบข้อนั้นซิ ตาบ้า! 🙄\n\n" + get_confirmation_summary(state["answers"])
                                ])
                                
                    # สเต็ปที่ 9: รับคำตอบใหม่ที่แก้ไขแล้ว
                    elif current_step == 9:
                        edit_num = state.get("editing_step", 1)
                        keys = {1: "name", 2: "age", 3: "gender", 4: "occupation", 5: "genre", 6: "relation", 7: "scene"}
                        target_key = keys.get(edit_num, "name")
                        
                        # บันทึกค่าแก้ไข
                        state["answers"][target_key] = user_text
                        state["step"] = 8 # กลับไปหน้ายืนยันข้อมูล
                        state["editing_step"] = None
                        
                        reply_message(reply_token, [
                            f"แก้ไขข้อมูลข้อที่ {edit_num} เรียบร้อยแล้วย่ะ! 😤\n\n" + get_confirmation_summary(state["answers"])
                        ])
                
                # ถ้าคุยเล่นทั่วไป (Free-form Chat)
                else:
                    # ตรวจสอบว่าผู้ใช้พิมพ์ แก้ไข [หมายเลข] เพื่อมาปรับสเปคตัวละครเดิมย้อนหลังหรือไม่
                    match = re.search(r'(?:แก้ไข|แก้)\s*([1-7])', user_text)
                    if match and state["answers"].get("name"):
                        edit_num = int(match.group(1))
                        state["in_interview"] = True
                        state["editing_step"] = edit_num
                        state["step"] = 9
                        
                        prefix = f"หืม? จะกลับมาแก้ไขสเปคตัวละคร '{state['answers']['name']}' ย้อนหลังงั้นหรอ? 🙄 ได้สิ...\n\n"
                        prompt_by_num = {
                            1: "เปลี่ยนชื่อตัวละครเป็นอะไรดีล่ะ? พิมพ์ชื่อใหม่มาเลยย่ะ! 👤",
                            2: "เปลี่ยนอายุตัวละครเป็นเท่าไหร่? พิมพ์อายุใหม่มาเลยย่ะ! 🎂",
                            3: "เปลี่ยนเพศตัวละครเป็นเพศไหน? พิมพ์เพศใหม่มาเลยย่ะ! ⚧️",
                            4: "เปลี่ยนอาชีพตัวละครเป็นอะไร? พิมพ์อาชีพใหม่มาเลยย่ะ! 💼",
                            5: "เปลี่ยนแนวเรื่อง/ธีมเป็นอะไรล่ะ? พิมพ์แนวใหม่มาเลย! 🎬",
                            6: "เปลี่ยนความสัมพันธ์กับ {{{{user}}}} เป็นแบบไหน? พิมพ์สเปคใหม่มาเลย! ⛓️",
                            7: "เปลี่ยนฉากเริ่มต้นเปิดเรื่องเป็นแบบไหน? พิมพ์รายละเอียดฉากใหม่มาเลย! 🌧️"
                        }
                        reply_message(reply_token, [prefix + prompt_by_num.get(edit_num, "ระบุข้อที่ถูกต้องสิย่ะ!")])
                    
                    else:
                        # คุยเล่นผ่าน Gemini
                        reply_text = generate_free_chat_gemini(user_text)
                        reply_message(reply_token, [reply_text])
                    
    except Exception as e:
        print(f"Error handling event: {e}")
        
    return 'OK'

if __name__ == "__main__":
    app.run(port=5000)
