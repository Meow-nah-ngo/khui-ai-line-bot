# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.parse
import urllib.error
import threading
from flask import Flask, request

app = Flask(__name__)

# 🔑 LINE & Gemini API Credentials
CHANNEL_ACCESS_TOKEN = "cJ5z7ciA1zbeT2NaG0piI9hlaV8PlTsuyk1uITYyDiuTKPkkzGuA3CZyzV6PDydrJ/jatnBOlxRMhYp9TQsYZeIqpz1mHUgHK3LDZr1t16Z9Inq67txbBnV+TsY8pypvs+sj8jUrpbubUuThHG7p2wdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "93a67dc472e7ec30ad50892849b80a63"
GEMINI_API_KEY = "AQ.Ab8RN6I0s1nebdgVc18Q6YzfI0LxzsY1oW3tvkmzX0iH_StAkQ"
ALLOWED_USER_ID = "U3492288d7c4c50b83572e5af0a84bd06"

# 🧠 หน่วยความจำสถานะการคุยของผู้เล่น (Conversation Session State)
user_states = {}

# ✉️ Helper Function: Reply Message
def reply_message(reply_token, messages):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": msg} for msg in messages[:5]]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print(f"Reply failed: {e}")

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
        "✨ เสน่ห์หรือกลิ่นประจำตัว: (บรรยายฟีลลิ่ง น้ำหอม หรือกลิ่นอายที่แผ่ออกมาจากตัวละครที่กระตุ้นอารมณ์ได้ดี)\n"
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
        f"แนวเรื่อง / ธีม: {answers.get('genre')}\n"
        f"ชื่อตัวละคร (บอท): {answers.get('name')}\n"
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

# ⚙️ กระบวนการเบื้องหลัง: เจนภาพ/ข้อความ และส่ง Push กลับเข้า Line
def process_and_send(user_id, answers):
    result = generate_character_gemini(answers)
    
    if not result:
        push_message(user_id, ["ขออภัยด้วยค่ะคุณกิ๊ฟฟี่ ระบบ AI ขัดข้องในการเรียบเรียงเนื้อหา ลองพิมพ์ 'เริ่มใหม่' เพื่อคุยสเปคบอทใหม่อีกครั้งนะคะ 🥺"])
        return
        
    messages = [
        "👾 [ส่วนที่ 1: ประวัติตัวละคร]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องประวัติตัวละคร)*\n\n" + result.get("bio", "ไม่มีข้อมูล"),
        "👥 [ส่วนที่ 2: บทบาทผู้เล่น]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องบทบาท)*\n\n" + result.get("role", "ไม่มีข้อมูล"),
        "🌧️ [ส่วนที่ 3: สถานการณ์]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องสถานการณ์)*\n\n" + result.get("scenario", "ไม่มีข้อมูล"),
        "💬 [ส่วนที่ 4: คำทักทายเริ่มต้น]\n*(คัดลอกข้อความด้านล่างนี้ไปใส่ในช่องคำทักทายเริ่มต้น)*\n\n" + result.get("greeting", "ไม่มีข้อมูล"),
        "✨ ปั้นตัวละครเสร็จสมบูรณ์เรียบร้อยแล้วค่ะ! หากต้องการสร้างตัวใหม่พิมพ์คำว่า 'เริ่มใหม่' หรือบอกพล็อตใหม่ได้เลยนะคะ 🖤"
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
                
                # คำสั่งเริ่มใหม่
                if user_text == "เริ่มใหม่" or user_text == "ยกเลิก" or user_id not in user_states:
                    user_states[user_id] = {
                        "step": 1,
                        "answers": {"name": "", "genre": "", "relation": "", "scene": ""}
                    }
                    reply_message(reply_token, [
                        "ยินดีต้อนรับสู่ระบบผู้ช่วยปั้นบอท Khui AI (เวอร์ชันสั่งการอัปเกกวดล่าสุด) ค่ะคุณกิ๊ฟฟี่! 🎨✨\n\nมาเริ่มคุยไอเดียสเปคบอทกันทีละขั้นตอนนะคะ (พิมพ์ 'เริ่มใหม่' เพื่อเริ่มใหม่ได้ตลอดเวลาค่ะ)\n\n👉 **ขั้นตอนที่ 1:** บอทของคุณชื่ออะไรคะ? (พิมพ์ระบุชื่อตัวละคร เช่น คิง, อคิน, คิม)"
                    ])
                    continue
                
                state = user_states[user_id]
                current_step = state["step"]
                
                # สเต็ปที่ 1: ชื่อบอท
                if current_step == 1:
                    state["answers"]["name"] = user_text
                    state["step"] = 2
                    reply_message(reply_token, [
                        f"บันทึกชื่อตัวละคร: '{user_text}' เรียบร้อยค่ะ 👤\n\n👉 **ขั้นตอนที่ 2:** แนวเรื่อง / ธีม ของบอทตัวนี้คือแนวไหนคะ? (เช่น มาเฟียคาสิโน, รักใสๆ อบอุ่น, แฟนเก่าหึงโหดปากจัด, คู่ปรับสนามซิ่งดุดัน 18+)"
                    ])
                    
                # สเต็ปที่ 2: แนวเรื่อง
                elif current_step == 2:
                    state["answers"]["genre"] = user_text
                    state["step"] = 3
                    reply_message(reply_token, [
                        f"บันทึกแนวเรื่อง/ธีม: '{user_text}' เรียบร้อยค่ะ 🎬\n\n👉 **ขั้นตอนที่ 3:** ความสัมพันธ์ระหว่างบอทกับผู้เล่น ({{user}}) เป็นอย่างไรคะ? (เช่น เจ้าหนี้มาเฟียรายใหญ่กับลูกหนี้ช่างแต่งหน้า, คู่อริที่เคยแข่งรถแพ้กูแล้วเนียนมาเกาะแกะ)"
                    ])
                    
                # สเต็ปที่ 3: ความสัมพันธ์
                elif current_step == 3:
                    state["answers"]["relation"] = user_text
                    state["step"] = 4
                    reply_message(reply_token, [
                        f"บันทึกความสัมพันธ์: '{user_text}' เรียบร้อยค่ะ ⛓️\n\n👉 **ขั้นตอนที่ 4:** ฉากเริ่มต้นเปิดตัว เกิดที่ไหนและสถานการณ์เป็นอย่างไรคะ? (เช่น ห้องทำงานส่วนตัวของมาเฟียตอนไฟดับพายุเข้าสะเทือนตึก, ในห้องจูนเครื่องยนต์ตอนฟ้าร้องไฟดับและกูตื่นกลัว)"
                    ])
                    
                # สเต็ปที่ 4: ฉากเริ่มต้น -> เริ่มรัน AI
                elif current_step == 4:
                    state["answers"]["scene"] = user_text
                    answers = state["answers"]
                    user_states.pop(user_id)
                    
                    reply_message(reply_token, [
                        "ได้รับข้อมูลสเปคตัวละครครบถ้วนเรียบร้อยแล้วค่ะ! 🚀\n\nกำลังเริ่มประมวลผลแต่งประวัติและสเปคตัวละครลึกซึ้งชนลิมิต Khui AI รอกล่องข้อความถัดไปประมาณ 30 วินาทีนะค้า... 🖤"
                    ])
                    
                    threading.Thread(target=process_and_send, args=(user_id, answers)).start()
                
    except Exception as e:
        print(f"Error handling event: {e}")
        
    return 'OK'

if __name__ == "__main__":
    app.run(port=5000)
