import discord
from discord.ext import commands
import requests
import json
import random
import asyncio
import re
import logging
from datetime import datetime

import os
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GAS_URL = os.getenv("GAS_URL")

intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용을 읽을 수 있도록 설정

bot = commands.Bot(command_prefix="!", intents=intents)

class ConfirmView(discord.ui.View):
    def __init__(self, ctx, payload, success_message, error_message, payload_type="generic", game_number=None):
        """
        ✅ 범용적으로 사용할 수 있는 확인용 View
        :param ctx: 명령어 호출한 유저 정보
        :param payload: GAS 요청 데이터
        :param success_message: 성공 시 출력할 메시지 (문자열 or 함수)
        :param error_message: 실패 시 출력할 메시지
        :param payload_type: "generic" (기본) or "game_result" (경기 결과 등록/삭제)
        """
        super().__init__(timeout=30)
        self.ctx = ctx
        self.payload = payload
        self.success_message = success_message  # 문자열 또는 콜백 함수
        self.error_message = error_message
        self.payload_type = payload_type  # "generic" | "game_result"
        self.game_number = game_number

        # ✅ 로깅 설정 (DEBUG 모드 활성화)
        logging.basicConfig(level=logging.DEBUG)
        logging.info(f"📌 ConfirmView 생성됨 (Payload: {self.payload})")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """✅ 버튼을 누른 사용자가 명령어를 입력한 유저인지 확인"""
        logging.debug(f"👤 [확인] {interaction.user} 가 버튼 클릭 (입력한 유저: {self.ctx.author})")
        return interaction.user == self.ctx.author

    async def send_followup(self, interaction: discord.Interaction, message: str):
        """✅ 처리 중 메시지 전송"""
        logging.debug(f"⏳ [처리 중] {message}")
        return await interaction.followup.send(f"⌛ {message} 잠시만 기다려주세요!")

    def extract_game_number(self, response_text: str) -> str:
        """✅ GAS 응답에서 게임번호 추출 (JSON or 정규식)"""
        logging.debug(f"📥 [응답 분석] 원본 응답: {response_text}")
        try:
            data = json.loads(response_text.strip().strip('"'))
            return data.get("game_number", "알 수 없음")
        except json.JSONDecodeError:
            match = re.search(r"게임번호:\s*(\d+)", response_text)
            return match.group(1) if match else "알 수 없음"

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """✅ 확인 버튼을 눌렀을 때 실행"""
        await interaction.response.defer()
        followup_message = await self.send_followup(interaction, "처리 중입니다.")

        try:
            logging.info(f"🚀 [요청 전송] Payload: {self.payload}")
            response = await asyncio.to_thread(requests.post, GAS_URL, json=self.payload)

            # ✅ 디버깅: 응답 상태 코드와 내용 출력
            logging.info(f"🚀 [응답 코드] {response.status_code}")
            logging.debug(f"📥 [응답 본문] {response.text}")

            if response.status_code != 200:
                raise requests.HTTPError(f"응답 코드 {response.status_code}")

            response_text = response.text.strip().strip('"')

            # ✅ "game_result" 타입인 경우, 경기번호 포함 메시지 생성
            if self.payload_type == "game_result":
                game_number = self.extract_game_number(response_text)
                message = self.success_message(game_number) if callable(self.success_message) else self.success_message
            else:
                message = self.success_message  # 일반적인 명령어 처리

            logging.info(f"✅ [성공] 응답 처리 완료 → {message}")
            await followup_message.edit(content=message)

        except (requests.RequestException, Exception) as e:
            logging.error(f"🚨 [오류] {e}")
            await followup_message.edit(content=f"🚨 {self.error_message}\n오류: {str(e)}")

        self.stop()

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """❌ 취소 버튼을 눌렀을 때 실행"""
        logging.info(f"🚫 [취소] {self.ctx.author} 님이 요청을 취소함")
        await interaction.response.send_message("🚫 작업이 취소되었습니다.", ephemeral=True)
        self.stop()


@bot.event
async def on_ready():
    print(f'✅ {bot.user}로 로그인 완료!')

import requests
import logging
import re

import logging

@bot.command()
async def 등록(ctx, username: str = None, classname: str = None, *, nickname: str = None):
    """
    ✅ 유저 등록 / 업데이트 명령어 (대화형 입력 추가)
    """
    logging.basicConfig(level=logging.INFO)

    logging.info("🚀 [등록 명령어 호출] username: %s, classname: %s, nickname: %s", username, classname, nickname)

    # ✅ 유저명이 없으면 입력받기
    if username is None:
        await ctx.send("🎮 **등록할 유저명을 입력하세요! (30초 내 입력)**")

        try:
            msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
            username = msg.content.strip()
            logging.info(f"✅ [입력 완료] 유저명: {username}")
        except asyncio.TimeoutError:
            await ctx.send("⏳ **시간 초과! 다시 `!등록` 명령어를 입력하세요.**")
            return

    def get_existing_users_and_aliases():
        """GAS에서 모든 유저명과 별명을 가져오는 함수"""
        try:
            logging.info("🔍 GAS에서 기존 유저 및 별명 데이터를 가져오는 중...")
            response = requests.get(f"{GAS_URL}?action=getUsersAndAliases")
            if response.status_code == 200:
                data = response.json()
                logging.info("✅ GAS 유저 및 별명 데이터 가져오기 성공!")
                return data.get("users", []), data.get("aliases", {})  # 유저 리스트, 유저별 별명 딕셔너리 반환
            else:
                logging.warning(f"⚠ GAS 데이터 가져오기 실패! HTTP {response.status_code}")
                return [], {}
        except Exception as e:
            logging.error(f"🚨 GAS 요청 중 오류 발생: {e}")
            return [], {}

    existing_users, existing_aliases = get_existing_users_and_aliases()
    logging.info(f"📋 기존 등록된 유저명: {existing_users}")
    logging.info(f"📋 기존 등록된 별명 목록: {existing_aliases}")

    # ✅ 닉네임 목록 변환 (모든 유저의 닉네임을 하나의 리스트로 변환)
    all_existing_nicknames = {alias for alias_list in existing_aliases.values() for alias in alias_list}

    # ✅ 1️⃣ 유저명이 기존 닉네임과 중복인지 확인
    if username and username in all_existing_nicknames:
        logging.warning(f"⚠ [중복 확인] `{username}` 이(가) 기존 닉네임과 중복됨!")
        await ctx.send(f"🚨 **유저명 `{username}`은(는) 다른 유저의 닉네임으로 사용 중입니다!** 다른 유저명을 입력하세요.")
        return

    # ✅ 2️⃣ 닉네임 중복 검사 (닉네임이 있을 경우)
    if nickname:
        if nickname in existing_users:
            await ctx.send(f"🚨 **닉네임 `{nickname}`은(는) 다른 유저의 유저명으로 사용 중입니다!** 다른 닉네임을 입력하세요.")
            return

        if nickname in all_existing_nicknames:
            await ctx.send(f"🚨 **닉네임 `{nickname}`은(는) 이미 사용 중입니다!** 다른 닉네임을 입력하세요.")
            return

    # ✅ 기존 유저 여부 확인
    is_update = username in existing_users
    logging.info(f"📝 기존 유저 여부 확인: {is_update}")

    # ✅ 클래스명 정렬 및 포맷 변환 (드/어/넥/슴 → 드, 어, 넥, 슴)
    valid_classes = ["드", "어", "넥", "슴"]
    if classname:
        classname = classname.replace("/", ",")  # ✅ 슬래시 → 콤마 변경
        classname_list = classname.split(",")
        classname_list = sorted(set(c.strip() for c in classname_list if c.strip() in valid_classes),
                                key=lambda x: valid_classes.index(x))
        classname = ",".join(classname_list)
        logging.info(f"🛠 클래스 정리 완료: {classname}")

    # ✅ GAS로 등록 요청 (기존 유저면 업데이트)
    payload = {
        "action": "register",
        "username": username,
        "classname": classname if classname else None,
        "nickname": nickname if nickname else None
    }

    logging.info(f"🚀 [GAS 요청 전송] Payload: {payload}")

    # ✅ 메시지 설정
    if is_update:
        confirm_msg = f"✅ `{username}` 님의 정보가 **업데이트**됩니다!\n"
        if classname:
            confirm_msg += f"- 클래스: `{classname}`\n"
        if nickname:
            confirm_msg += f"- 닉네임: `{nickname}`"
        error_msg = "🚨 정보 업데이트에 실패했습니다."
    else:
        confirm_msg = f"✅ `{username}` 님이 **새로 등록**됩니다!"
        error_msg = "🚨 등록 요청에 실패했습니다."

    view = ConfirmView(ctx, payload, confirm_msg, error_msg)

    logging.info("✅ 등록 요청 완료, 사용자 확인 대기 중...")
    await ctx.send(f"📋 `{username}` 님을 등록(또는 업데이트)하시겠습니까?", view=view)

@bot.command()
async def 별명등록(ctx, username: str = None, *, aliases: str = None):
    """유저의 별명을 등록하는 명령어"""

    logging.basicConfig(level=logging.INFO)
    logging.info(f"🚀 [별명등록 명령어 실행] username: {username}, aliases: {aliases}")

    def get_existing_users_and_aliases():
        """GAS에서 모든 유저명과 별명을 가져오는 함수"""
        try:
            logging.info("🔍 GAS에서 기존 유저 및 별명 데이터를 가져오는 중...")
            response = requests.get(f"{GAS_URL}?action=getUsersAndAliases")
            if response.status_code == 200:
                data = response.json()
                logging.info("✅ GAS 유저 및 별명 데이터 가져오기 성공!")
                return data.get("users", []), data.get("aliases", {})  # 유저 리스트, 유저별 별명 딕셔너리 반환
            else:
                logging.warning(f"⚠ GAS 데이터 가져오기 실패! HTTP {response.status_code}")
                return [], {}
        except Exception as e:
            logging.error(f"🚨 GAS 요청 중 오류 발생: {e}")
            return [], {}

    existing_users, existing_aliases = get_existing_users_and_aliases()
    logging.info(f"📋 기존 등록된 유저명: {existing_users}")
    logging.info(f"📋 기존 등록된 별명 목록: {existing_aliases}")

    def check_duplicate(new_aliases, username):
        """새로운 별명이 기존 유저명 또는 다른 유저의 별명과 중복되는지 확인"""
        user_existing_aliases = existing_aliases.get(username, [])  # ✅ 해당 유저의 기존 별명
        all_existing_aliases = {alias for user, alias_list in existing_aliases.items() if user != username for alias in alias_list}

        duplicate_with_users = [alias for alias in new_aliases if alias in existing_users]  # ✅ 유저명과 중복 체크
        duplicate_with_others = [alias for alias in new_aliases if alias in all_existing_aliases]
        duplicate_with_self = [alias for alias in new_aliases if alias in user_existing_aliases]

        logging.info(
            f"🔍 입력한 별명: {new_aliases} | 중복된 별명(유저명): {duplicate_with_users} | "
            f"중복된 별명(다른 유저): {duplicate_with_others} | 중복된 별명(본인): {duplicate_with_self}"
        )

        return duplicate_with_users, duplicate_with_others, duplicate_with_self

    async def request_new_alias(ctx, username):
        """사용자로부터 별명을 입력받는 함수 (중복되지 않는 별명을 받을 때까지 실행)"""
        attempts = 2
        while attempts > 0:
            try:
                await ctx.send(f"✏️ `{username}` 님의 별명을 입력하세요! (쉼표 또는 슬래시 구분, 남은 시도 {attempts}회)")
                msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
                alias_list = [alias.strip() for alias in re.split(r"[,/]", msg.content)]

                if not alias_list:
                    await ctx.send("🚨 **별명을 입력해야 합니다!** 다시 입력해주세요.")
                    logging.warning("⚠ 입력된 별명이 없음")
                    attempts -= 1
                    continue

                duplicate_with_users, duplicate_with_others, duplicate_with_self = check_duplicate(alias_list, username)

                if not duplicate_with_users and not duplicate_with_others and not duplicate_with_self:
                    logging.info(f"✅ 새로운 별명 입력 완료: {alias_list}")
                    return alias_list

                error_messages = []
                if duplicate_with_users:
                    error_messages.append(f"❌ **유저명과 중복된 별명** `{', '.join(duplicate_with_users)}`")
                if duplicate_with_others:
                    error_messages.append(f"❌ **다른 유저가 이미 사용 중인 별명** `{', '.join(duplicate_with_others)}`")
                if duplicate_with_self:
                    error_messages.append(f"❌ **이미 `{username}` 님이 사용 중인 별명** `{', '.join(duplicate_with_self)}`")

                await ctx.send("\n".join(error_messages))
                logging.warning(f"⚠ 중복된 별명 입력됨: {error_messages}")
                attempts -= 1

            except asyncio.TimeoutError:
                logging.error(f"⏳ `{username}` 님이 30초 내 입력하지 않음.")
                await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!별명등록`을 입력하세요!")
                return None

        await ctx.send("🚨 너무 많은 시도 횟수 초과! 다시 `!별명등록`을 입력하세요.")
        logging.warning("🚨 별명 입력 시도 횟수 초과!")
        return None

    # ✅ 유저명 입력 확인
    if not username:
        await ctx.send("🎮 별명을 등록할 유저명을 입력하세요! (30초 내 입력)")
        try:
            msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
            username = msg.content.strip()
            logging.info(f"📋 입력된 유저명: {username}")
        except asyncio.TimeoutError:
            await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!별명등록`을 입력하세요!")
            logging.error("⏳ 유저명 입력 시간 초과!")
            return

    if not aliases:
        alias_list = await request_new_alias(ctx, username)
        if alias_list is None:
            return
    else:
        alias_list = [alias.strip() for alias in re.split(r"[,/]", aliases)]
        duplicate_with_users, duplicate_with_others, duplicate_with_self = check_duplicate(alias_list, username)

        if duplicate_with_users or duplicate_with_others or duplicate_with_self:
            error_messages = []
            if duplicate_with_users:
                error_messages.append(f"❌ **유저명과 중복된 별명** `{', '.join(duplicate_with_users)}`")
            if duplicate_with_others:
                error_messages.append(f"❌ **다른 유저가 이미 사용 중인 별명** `{', '.join(duplicate_with_others)}`")
            if duplicate_with_self:
                error_messages.append(f"❌ **이미 `{username}` 님이 사용 중인 별명** `{', '.join(duplicate_with_self)}`")

            await ctx.send("\n".join(error_messages))
            logging.warning(f"⚠ 중복된 별명 입력됨: {error_messages}")
            alias_list = await request_new_alias(ctx, username)
            if alias_list is None:
                return

    payload = {
        "action": "registerAlias",
        "username": username,
        "aliases": alias_list
    }
    logging.info(f"🚀 GAS로 전송할 데이터: {payload}")

    view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 별명이 등록되었습니다: {', '.join(alias_list)}",
                       "🚨 별명 등록 요청에 실패했습니다.")

    logging.info(f"✅ `{username}` 님의 별명 등록 요청 완료! 별명: {alias_list}")
    await ctx.send(f"📋 `{username}` 님의 별명을 `{', '.join(alias_list)}` (으)로 등록하시겠습니까?", view=view)

@bot.command()
async def 조회(ctx, username: str = None):
    """
    ✅ 새로운 Results 시트 구조 반영
    """
    logging.basicConfig(level=logging.INFO)

    if not username:
        await ctx.send("🔍 조회할 유저명을 입력하세요! 예시: `!조회 규석문`")
        logging.warning("⚠ 조회 명령어 실행 - 유저명이 입력되지 않음!")
        return

    logging.info(f"🚀 [조회 명령어 실행] username: {username}")

    payload = {"action": "getUserInfo", "username": username}
    logging.info(f"📡 GAS로 데이터 요청: {payload}")

    response = requests.post(GAS_URL, json=payload)
    raw_response = response.text  # 🔍 원본 응답 저장 (디버깅 용도)

    logging.info(f"🔍 GAS 응답 코드: {response.status_code}")
    logging.info(f"🔍 GAS 응답 본문: {raw_response}")

    try:
        data = response.json()
        logging.info(f"✅ GAS 응답 JSON 디코딩 성공! 데이터: {data}")
    except requests.exceptions.JSONDecodeError:
        logging.error(f"🚨 JSON 디코딩 오류 발생! 원본 응답: {raw_response}")
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{raw_response}`")
        return

    if "error" in data:
        logging.warning(f"⚠ GAS 응답에서 오류 발생: {data['error']}")
        await ctx.send(f"🚨 {data['error']}")
        return

    # ✅ 데이터 가공 후 출력
    msg = (
        f"📜 **`{data.get('username', '알 수 없음')}` 님의 정보**\n"
        f"\n🛡 **플레이 가능 클래스:** {data.get('class', '[Data 없음]')}\n"
        f"🎭 **별명:** {data.get('nickname', '[Data 없음]')}\n"
        f"📅 **마지막 경기 일시:** {data.get('last_game', '[Data 없음]')}\n"
        f"🏆 **이번 시즌 전체 승수:** {data.get('season_wins', 0)}승"
    )

    logging.info(f"✅ 최종 조회 결과 출력: \n{msg}")

    await ctx.send(msg)

@bot.command()
async def 클래스(ctx, username: str = None, *, classes: str = None):
    """
    ✅ 유저의 클래스를 등록하는 명령어
    """
    logging.basicConfig(level=logging.INFO)

    valid_classes = ["드", "어", "넥", "슴"]  # ✅ 고정된 클래스 순서

    def format_classes(class_input):
        """✅ 입력받은 클래스 정리 및 중복 제거 후 정렬"""
        class_list = [c.strip() for c in re.split(r"[,/]", class_input)]
        class_list = sorted(set(class_list), key=lambda x: valid_classes.index(x) if x in valid_classes else len(valid_classes))
        return ", ".join(class_list)

    # ✅ 직접 입력 방식 (username + classes 함께 입력됨)
    if username and classes:
        logging.info(f"🚀 [클래스 등록 요청] username: {username}, classes: {classes}")
        formatted_classes = format_classes(classes)

        payload = {
            "action": "registerClass",
            "username": username,
            "classes": formatted_classes  # ✅ 정렬된 클래스 저장
        }
        logging.info(f"📡 GAS로 전송할 데이터: {payload}")

        view = ConfirmView(
            ctx, payload,
            f"✅ `{username}` 님의 클래스가 등록되었습니다: {formatted_classes}",
            "🚨 클래스 등록 요청에 실패했습니다."
        )

        await ctx.send(f"🛡 `{username}` 님의 클래스를 `{formatted_classes}` (으)로 등록하시겠습니까?", view=view)
        return

    # ✅ 대화형 모드
    logging.info("🔍 [클래스 등록 - 대화형 입력 시작]")
    await ctx.send("🎭 클래스를 등록할 유저명을 입력하세요! (30초 내 입력)")

    try:
        msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
        username = msg.content.strip()
        logging.info(f"📋 입력된 유저명: {username}")

        await ctx.send(f"🛡 `{username}` 님의 클래스를 입력하세요! (쉼표 또는 슬래시 구분, 예시: 드,어/넥,슴) (30초 내 입력)")

        msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
        formatted_classes = format_classes(msg.content)

        logging.info(f"📋 입력된 클래스: {formatted_classes}")

        payload = {
            "action": "registerClass",
            "username": username,
            "classes": formatted_classes
        }
        logging.info(f"📡 GAS로 전송할 데이터: {payload}")

        view = ConfirmView(
            ctx, payload,
            f"✅ `{username}` 님의 클래스가 등록되었습니다: {formatted_classes}",
            "🚨 클래스 등록 요청에 실패했습니다."
        )

        await ctx.send(f"🛡 `{username}` 님의 클래스를 `{formatted_classes}` (으)로 등록하시겠습니까?", view=view)

    except asyncio.TimeoutError:
        logging.warning("⏳ 시간이 초과되었습니다. 유저 입력 없음.")
        await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!클래스`를 입력하세요!")


import logging

@bot.command()
async def 결과등록(ctx, *, input_text: str = None):
    """
    ✅ !결과등록 명령어: 승리팀과 패배팀을 입력하면 경기 결과를 등록
    """
    logging.basicConfig(level=logging.INFO)

    logging.info(f"📥 `!결과등록` 명령어 실행 → {ctx.author} ({ctx.author.id}) | 입력: {input_text}")

    if input_text:
        logging.info(f"🔍 입력된 경기 결과 파싱 시작: {input_text}")

        # ✅ **스코어 총합 초과 검사 (9점 초과 시 오류)**
        raw_scores = re.findall(r'\d+', input_text)
        logging.info(f"🔢 추출된 점수: {raw_scores}")

        if len(raw_scores) >= 2:
            win_score, lose_score = map(int, raw_scores[:2])
            total_score = win_score + lose_score

            logging.info(f"🏆 승리팀 점수: {win_score}, ❌ 패배팀 점수: {lose_score}, 🔄 총합: {total_score}")

            if total_score > 9:
                logging.warning(f"🚨 점수 총합 초과! {total_score}점 (최대 9점 가능)")
                await ctx.send(
                    f"🚨 **결과 등록 불가** ⚠\n"
                    f"→ `{input_text}`\n"
                    "❌ **양 팀 스코어의 합이 9를 초과하므로, 등록할 수 없습니다!**"
                )
                return

        win_players, lose_players, win_score, lose_score = parse_match_input(input_text)

        logging.info(f"🏆 승리팀: {win_players}, ❌ 패배팀: {lose_players}, 🏅 스코어: {win_score}-{lose_score}")

        if win_players is None or lose_players is None:
            logging.warning(f"🚨 입력 형식 오류: {input_text}")
            await ctx.send(
                "🚨 **잘못된 형식입니다!**\n"
                "`!결과등록 [아래5]유저1,유저2,유저3,유저4 vs [위4]유저5,유저6,유저7,유저8`\n"
                "✅ **순서 주의:** 반드시 `드,어,넥,슴` 클래스 순서대로 입력해야 합니다."
            )
            return

        # ✅ **승리 팀 스코어는 무조건 5점이어야 함**
        if win_score != 5:
            logging.warning(f"🚨 승리팀 점수 오류! (승리팀 점수: {win_score}, 반드시 5점이어야 함)")
            await ctx.send(
                f"🚨 **결과 등록 불가** ⚠\n"
                f"→ `{input_text}`\n"
                "❌ **승리 팀의 스코어는 반드시 5점이어야 합니다!**"
            )
            return

        await validate_and_register(ctx, win_players, lose_players, win_score, lose_score)
        return

    # ✅ 대화형 입력 모드
    logging.info("📝 대화형 입력 모드 활성화")
    await ctx.send(
        "🏆 **경기 결과를 입력하세요!**\n"
        "예시: `!결과등록 [아래5]유저1,유저2,유저3,유저4 vs [위4]유저5,유저6,유저7,유저8`\n"
        "✅ **순서 주의:** 반드시 `드,어,넥,슴` 클래스 순서대로 입력해야 합니다."
    )


async def validate_and_register(ctx, win_players, lose_players, win_score, lose_score):
    """
    ✅ 유저 등록 여부 확인 후 경기 등록 진행
    """
    logging.info(f"✅ 유저 등록 여부 확인 중: {win_players + lose_players}")

    # 명령어 실행한 유저 정보 추가
    submitted_by = ctx.author.display_name  # 디스코드 닉네임 가져오기
    logging.info(f"📢 경기 결과 등록 요청자: {submitted_by}")

    all_players = win_players + lose_players
    response = requests.post(GAS_URL, json={"action": "getPlayersInfo", "players": all_players})

    if response.status_code != 200:
        logging.error(f"❌ 서버 응답 오류: {response.status_code}, 내용: {response.text}")
        await ctx.send("🚨 서버 응답 오류로 인해 경기 등록을 진행할 수 없습니다. 다시 시도해주세요.")
        return

    data = response.json()
    logging.info(f"📜 GAS 응답 데이터: {data}")

    if "error" in data:
        logging.warning(f"🚨 GAS 응답 오류: {data['error']}")
        await ctx.send(f"🚨 {data['error']}")
        return

    registered_users = {player["username"] for player in data["players"]}
    unregistered_users = [p for p in all_players if p not in registered_users]

    if unregistered_users:
        logging.warning(f"⛔ 등록되지 않은 유저 발견: {unregistered_users}")
        await ctx.send(f"🚨 등록되지 않은 유저가 포함되어 있습니다: {', '.join(unregistered_users)}")
        return

    # ✅ 경기번호 생성
    game_number = datetime.now().strftime("%y%m%d%H%M")
    logging.info(f"🎮 생성된 경기번호: {game_number}")

    payload = {
        "action": "registerResult",
        "game_number": game_number,
        "winners": win_players,
        "losers": lose_players,
        "win_score": win_score,
        "lose_score": lose_score,
        "submitted_by": submitted_by  # ✅ 추가: 경기 등록자 닉네임
    }
    logging.info(f"🚀 경기 결과 등록 요청 데이터: {payload}")

    view = ConfirmView(
        ctx,
        payload,
        lambda x: f"✅ 경기 결과가 기록되었습니다! **[게임번호: {game_number}]**\n"
                  f"🏆 **승리 팀:** {format_team(win_players)} (스코어: {win_score})\n"
                  f"❌ **패배 팀:** {format_team(lose_players)} (스코어: {lose_score})\n"
                  f"👤 **등록자:** {submitted_by}",
        "🚨 경기 등록 요청에 실패했습니다.",
        payload_type="game_result",
        game_number=game_number
    )

    await ctx.send(
        f"📊 **승리 팀:** {format_team(win_players)} (스코어: {win_score})\n"
        f"❌ **패배 팀:** {format_team(lose_players)} (스코어: {lose_score})\n"
        f"👤 **등록자:** {submitted_by}\n\n"
        f"경기 결과를 등록하시겠습니까?",
        view=view
    )

def parse_match_input(input_text):
    """
    ✅ 경기 결과 텍스트에서 승리/패배 팀을 추출하는 함수
    """
    logging.info(f"📝 경기 결과 분석 중: {input_text}")

    match = re.match(r"\[아래(\d+)]\s*(.+?)\s*vs\s*\[위(\d+)]\s*(.+)", input_text)

    if not match:
        logging.warning(f"🚨 입력 형식 오류: {input_text}")
        return None, None, None, None

    below_score = int(match.group(1))
    above_score = int(match.group(3))
    below_players = [p.strip() for p in match.group(2).split("/") if p.strip()]
    above_players = [p.strip() for p in match.group(4).split("/") if p.strip()]

    if len(below_players) != 4 or len(above_players) != 4:
        logging.warning(f"🚨 플레이어 수 오류: {below_players} vs {above_players}")
        return None, None, None, None

    if below_score > above_score:
        return below_players, above_players, below_score, above_score
    elif above_score > below_score:
        return above_players, below_players, above_score, below_score
    else:
        logging.warning(f"🚨 동점 경기 발생: {input_text}")
        return None, None, None, None

def format_team(team):
    """
    ✅ 유저명 + 클래스 포맷 적용
    """
    class_order = ["드", "어", "넥", "슴"]
    return ", ".join(f"{player}({class_order[i]})" for i, player in enumerate(team))



@bot.command()
async def 결과조회(ctx, game_number: str = None):
    """
    ✅ 특정 경기 조회 or 최근 경기 조회
    """
    logging.basicConfig(level=logging.INFO)
    logging.info(f"📥 `!결과조회` 명령어 입력됨. 입력된 game_number: {game_number}")

    # ✅ 특정 경기 조회 or 최근 경기 조회 선택
    if game_number:
        payload = {"action": "getMatch", "game_number": int(game_number)}
        logging.info(f"🔍 특정 경기 조회 요청: 게임번호 `{game_number}`")
    else:
        payload = {"action": "getRecentMatches"}
        logging.info("🔍 최근 5경기 조회 요청")

    logging.info(f"🚀 요청 URL: {GAS_URL}")
    logging.info(f"📡 전송 데이터: {payload}")

    try:
        response = requests.post(GAS_URL, json=payload)
        logging.info(f"📡 GAS 응답 상태 코드: {response.status_code}")
        logging.info(f"📜 GAS 응답 원본: {response.text}")

        data = response.json()
        logging.info(f"🔍 변환된 GAS 응답 (JSON): {json.dumps(data, indent=2, ensure_ascii=False)}")

    except requests.exceptions.JSONDecodeError:
        logging.error(f"🚨 JSON 변환 오류 발생! 원본 응답: {response.text}")
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    # ✅ 최근 5경기 조회
    if "matches" in data and len(data["matches"]) > 0:
        logging.info(f"✅ 최근 {len(data['matches'])}개 경기 데이터 감지됨!")
        msg = "📊 **최근 5경기 결과:**\n"

        for i, match in enumerate(data["matches"], start=1):
            logging.info(f"🧐 디버깅: match 데이터 = {match}")  # ✅ match 데이터 확인

            # ✅ 날짜 포맷 변경
            timestamp = match.get("timestamp", "알 수 없음")
            try:
                formatted_date = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
            except ValueError:
                formatted_date = timestamp  # 변환 실패 시 원래 값 사용
                logging.warning(f"⚠️ 날짜 변환 실패: `{timestamp}`")

            msg += f"`[{i}]` 🎮 **게임번호:** `{match.get('game_number', '알 수 없음')}`\n"
            msg += f"📅 **날짜:** {formatted_date}\n"
            msg += f"🏆 **승리 팀:** {match.get('winners', '데이터 없음')}\n"
            msg += f"❌ **패배 팀:** {match.get('losers', '데이터 없음')}\n\n"

        await ctx.send(msg)

    # ✅ 특정 경기 조회
    elif "game_number" in data:
        logging.info(f"✅ 개별 경기 데이터 감지됨: {data}")
        msg = f"📜 **경기 정보**\n"
        msg += f"🎮 **게임번호:** `{data.get('game_number', '알 수 없음')}`\n"
        msg += f"📅 **날짜:** {data.get('timestamp', '알 수 없음')}\n"
        msg += f"🏆 **승리 팀:** {data.get('winners', '데이터 없음')}\n"
        msg += f"❌ **패배 팀:** {data.get('losers', '데이터 없음')}"

        await ctx.send(msg)

    else:
        logging.warning("🚨 조회된 경기 기록이 없음!")
        await ctx.send("🚨 해당 경기 기록이 없습니다.")

@bot.command()
async def 결과삭제(ctx, game_number: str = None):
    """
    ✅ 특정 경기 기록을 삭제하는 명령어
    """
    logging.basicConfig(level=logging.INFO)
    logging.info(f"📥 `!결과삭제` 명령어 실행됨. 입력된 game_number: {game_number}")

    if not game_number:
        await ctx.send("🗑 삭제할 경기번호를 입력하세요! (30초 내 입력)")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            game_number = msg.content.strip()  # 사용자가 입력한 게임번호
            logging.info(f"✅ 입력된 게임번호: {game_number}")
        except asyncio.TimeoutError:
            logging.warning("⏳ 게임번호 입력 시간 초과됨.")
            await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!결과삭제`를 입력하세요!")
            return

    # ✅ 해당 경기의 정보를 먼저 조회
    payload = {"action": "getMatch", "game_number": game_number}
    logging.info(f"🚀 GAS 요청 URL: {GAS_URL}")
    logging.info(f"📡 전송 데이터: {payload}")

    response = requests.post(GAS_URL, json=payload)
    logging.info(f"📡 GAS 응답 상태 코드: {response.status_code}")
    logging.info(f"📜 GAS 응답 원본: {response.text}")

    try:
        data = response.json()
        logging.info(f"🔍 변환된 GAS 응답 (JSON): {json.dumps(data, indent=2, ensure_ascii=False)}")
    except requests.exceptions.JSONDecodeError:
        logging.error(f"🚨 JSON 변환 오류 발생! 원본 응답: {response.text}")
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    if "error" in data:
        logging.warning(f"🚨 GAS에서 오류 반환: {data['error']}")
        await ctx.send(f"🚨 {data['error']}")
        return

    # ✅ 승/패 팀 정보 가져오기 (리스트로 변환)
    win_players = data.get("winners", "").split(", ") if isinstance(data.get("winners"), str) else data.get("winners", [])
    lose_players = data.get("losers", "").split(", ") if isinstance(data.get("losers"), str) else data.get("losers", [])

    # ✅ 팀 데이터가 정상적으로 로드되었는지 확인
    logging.info(f"🏆 승리 팀: {win_players}")
    logging.info(f"❌ 패배 팀: {lose_players}")

    if not win_players or not lose_players:
        logging.error("🚨 경기 데이터가 비어 있음! 경기번호가 올바른지 확인 필요.")
        await ctx.send("🚨 경기 데이터를 가져올 수 없습니다. 경기번호를 확인하세요.")
        return

    def format_team(team):
        """ ✅ 유저명 + 클래스 순서 적용 """
        if not team or len(team) < 4:
            logging.warning("🚨 팀 데이터가 4명 이하로 감지됨! 데이터 손상 가능성 있음.")
            return "데이터 오류 (4명 부족)"

        return ", ".join(f"{player.strip()}" for i, player in enumerate(team[:4]))  # ✅ 4명까지만 적용

    win_team_info = format_team(win_players)
    lose_team_info = format_team(lose_players)

    # ✅ 삭제 확인 메시지
    delete_message = (
        f"⚠️ `{game_number}` 경기 기록을 삭제하시겠습니까?\n"
        f" - 삭제 [승] {win_team_info}\n"
        f" - 삭제 [패] {lose_team_info}"
    )
    logging.info(f"📋 삭제 전 최종 확인 메시지:\n{delete_message}")

    # ✅ 삭제 요청 전 확인
    delete_payload = {"action": "deleteMatch", "game_number": game_number}
    logging.info(f"🚀 GAS에 삭제 요청 전송: {delete_payload}")

    async def confirm_callback(interaction):
        response = requests.post(GAS_URL, json=delete_payload)
        logging.info(f"📡 GAS 응답 상태 코드 (삭제 요청): {response.status_code}")
        logging.info(f"📜 GAS 응답 원본 (삭제 요청): {response.text}")

        try:
            data = response.json()
            if "error" in data:
                logging.warning(f"🚨 GAS에서 삭제 요청 실패: {data['error']}")
                await ctx.send(f"🚨 오류: {data['error']}")
                return

            # ✅ 삭제 완료 메시지 (경기 정보 포함)
            result_message = (
                f"✅ `{game_number}` 경기 기록이 삭제되었습니다!\n"
                f" - 삭제 [승] {win_team_info}\n"
                f" - 삭제 [패] {lose_team_info}"
            )
            logging.info("✅ 경기 삭제 완료!")
            await ctx.send(result_message)

        except Exception as e:
            logging.error(f"🚨 경기 삭제 요청 중 예외 발생: {e}")
            await ctx.send("🚨 경기 삭제 요청에 실패했습니다.")

    result_message = (
        f"✅ `{game_number}` 경기 기록이 삭제되었습니다!\n"
        f" - 삭제 [승] {win_team_info}\n"
        f" - 삭제 [패] {lose_team_info}"
    )

    view = ConfirmView(
        ctx,
        delete_payload,
        result_message,
        "🚨 경기 삭제 요청에 실패했습니다.",
        payload_type="game_result",
        game_number=game_number
    )

    await ctx.send(delete_message, view=view)
import logging

@bot.command(aliases=["도움", "헬프", "명령어"])
async def 도움말(ctx):
    """
    ✅ 봇의 모든 명령어 목록을 출력하는 도움말 기능
    """
    logging.basicConfig(level=logging.INFO)
    logging.info(f"📥 `!도움말` 명령어 실행됨. 요청한 사용자: {ctx.author.name}")

    help_text = (
        "**📜 사용 가능한 명령어 목록:**\n"
        "```yaml\n"
        "\"!등록 [유저명]\" - 🆕 유저 등록\n"
        "\"!별명등록 [유저명] [별명1, 별명2, ...]\" - 🏷 유저 별명 추가\n"
        "\"!별명삭제 [유저명]\" - ❌ 유저 별명 삭제\n"
        "\"!삭제 [유저명]\" - ❌ 유저 삭제\n"
        "\"!조회 [유저명]\" - 🔍 유저 정보 조회\n"
        "\"!클래스 [유저명] [클래스명]\" - 🛡 유저 클래스 등록\n"
        "\"!결과등록 [아래*]유저1/유저2,... vs [위*]유저1/유저2,...\" (* = 경기스코어) - 📊 경기 결과 등록\n"
        "\"!결과조회 [게임번호]\" - 📄 경기 결과 조회\n"
        "\"!결과삭제 [게임번호]\" - 🗑 경기 기록 삭제\n"
        "\"!팀생성 [유저1, 유저2, ...]\" - 🤝 자동 팀 생성\n"
        "\"!팀생성고급 [유저1, 유저2, ...]\" - 🔒 자동 팀 생성 (관리자 전용)\n"
        "\"!MMR갱신\" - 🔄 전체 유저의 MMR 갱신 (관리자 전용)\n"
        "\"!홈페이지\" - 🌐 전적 기록실 이동\n"
        "\"!세팅\" - 🔧 캐릭터별 세팅 정보 보기\n"
        "\"!도움말\" - 📜 명령어 목록 확인\n"
        "```"
    )

    logging.info("📜 도움말 메시지 내용 준비 완료.")

    try:
        await ctx.send(help_text)
        logging.info("✅ 도움말 메시지 전송 성공!")
    except Exception as e:
        logging.error(f"🚨 도움말 메시지 전송 실패! 오류: {str(e)}")
        await ctx.send("🚨 도움말 메시지를 전송하는 중 오류가 발생했습니다!")

@bot.command()
async def 팀생성일반(ctx, *, players: str = None):
    """
    ✅ MMR 순위를 기반으로 1~4등 중 2명, 5~8등 중 2명을 뽑아 팀을 나눔
    ✅ 유저명뿐만 아니라 닉네임으로도 팀 생성 가능 (닉네임 → 유저명 변환)
    ✅ 포지션을 랜덤하게 섞되, 해당 플레이어가 가진 클래스만 배치됨
    """
    import random

    # ✅ 유저 입력 받기
    if not players:
        await ctx.send("🚨 **팀을 생성할 유저 목록을 입력하세요! (쉼표 또는 슬래시로 구분, 정확히 8명 입력 필수)**\n"
                       "⏳ **30초 내로 유저명을 입력해주세요!**")
        try:
            msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
            players = msg.content.strip()
        except asyncio.TimeoutError:
            await ctx.send("⏳ **시간 초과! 다시 `!팀생성` 명령어를 입력하세요.**")
            return

    player_list = list(set(re.split(r"[,/]", players.strip())))
    logging.info(f"🎯 입력된 유저 리스트: {player_list}")

    # ✅ GAS에서 유저명 & 닉네임 데이터 가져오기
    response = requests.get(f"{GAS_URL}?action=getUsersAndAliases")
    try:
        data = response.json()
        if "error" in data:
            await ctx.send(f"🚨 오류: {data['error']}")
            return
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    # ✅ 유저명 & 닉네임 매핑 정보
    username_list = data.get("users", [])  # ✅ 유저명 리스트
    alias_map = {alias: user for user, aliases in data.get("aliases", {}).items() for alias in aliases}  # 닉네임 → 유저명 매핑

    # ✅ 입력한 값들을 유저명으로 변환
    converted_players = []
    unknown_players = []
    for p in player_list:
        if p in username_list:
            converted_players.append(p)  # ✅ 원래 유저명 그대로 사용
        elif p in alias_map:
            converted_players.append(alias_map[p])  # ✅ 닉네임 → 유저명 변환
            logging.info(f"🔄 닉네임 `{p}` → 유저명 `{alias_map[p]}` 변환 완료")
        else:
            unknown_players.append(p)  # ❌ 찾을 수 없는 유저

    logging.info(f"🎯 **최종 변환된 유저 리스트:** {converted_players}")
    logging.info(f"🚨 **등록되지 않은 유저:** {unknown_players}")

    if len(converted_players) != 8:
        await ctx.send(f"🚨 **팀 생성 불가! 정확히 8명의 유저를 입력해야 합니다!**\n"
                       f"❌ **등록되지 않은 유저:** `{', '.join(unknown_players)}`")
        return

    # ✅ GAS에서 플레이어 정보 가져오기
    payload = {"action": "getPlayersInfo", "players": converted_players}
    response = requests.post(GAS_URL, json=payload)

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    if "error" in data:
        await ctx.send(f"🚨 {data['error']}")
        return

    players_data = data.get("players", [])
    if not players_data:
        await ctx.send(f"🚨 오류: 유저 정보를 가져오지 못했습니다.\n🔍 응답 내용: `{data}`")
        return

    registered_users = {p['username'] for p in players_data}
    missing_users = [p for p in converted_players if p not in registered_users]

    # ✅ **등록되지 않은 유저가 있으면 팀 생성 불가!**
    if missing_users:
        await ctx.send(f"🚨 **팀 생성 불가!** ❌\n"
                       f"⛔ **등록되지 않은 유저**: `{', '.join(missing_users)}`\n"
                       "📌 **해결 방법**: `!등록 [유저명]` 명령어로 유저를 등록한 후 다시 시도해주세요!")
        return

    # ✅ MMR 기준 정렬 (내림차순)
    players_data.sort(key=lambda x: x['mmr'], reverse=True)
    logging.info(f"📊 **MMR 순위 정렬된 유저 리스트:** {[(p['username'], p['mmr']) for p in players_data]}")

    # ✅ 팀 생성 및 검증 로직
    def create_balanced_teams():
        top_half = random.sample(players_data[:4], 2)  # 상위 4명 중 2명 선택
        bottom_half = random.sample(players_data[4:], 2)  # 하위 4명 중 2명 선택
        team1 = top_half + bottom_half
        team2 = [p for p in players_data if p not in team1]
        return team1, team2

    attempts = 0
    valid_teams = False
    while attempts < 10:
        team1, team2 = create_balanced_teams()
        logging.info(f"🎲 **랜덤 팀 배정 시도 {attempts+1}:** 팀1 - {team1}, 팀2 - {team2}")
        valid_teams = True  # 검증 로직 간소화 (필요하면 check_valid_teams 추가)
        if valid_teams:
            break
        attempts += 1

    if not valid_teams:
        await ctx.send("🚨 **팀 생성 실패! 유효한 조합을 찾을 수 없습니다.**")
        return

    # ✅ 팀 내 포지션 랜덤 배치
    def shuffle_team_roles(team):
        positions = ["드", "어", "넥", "슴"]
        random.shuffle(positions)
        shuffled_team = []
        for position in positions:
            available_players = [p for p in team if position in p["class"]]
            if available_players:
                selected_player = random.choice(available_players)
                shuffled_team.append({"username": selected_player["username"], "class": position})
                team.remove(selected_player)
        return shuffled_team

    team1 = shuffle_team_roles(team1)
    team2 = shuffle_team_roles(team2)

    logging.info(f"🔄 **팀1 최종 포지션:** {team1}")
    logging.info(f"🔄 **팀2 최종 포지션:** {team2}")

    # ✅ 최종 팀 배정 후 메시지 출력
    team1_names = "/".join([p['username'] for p in team1])
    team2_names = "/".join([p['username'] for p in team2])
    msg = f"[아래] {team1_names} vs [위] {team2_names}"

    await ctx.send(msg)

@bot.command()
async def 팀생성고급(ctx, *, players: str = None):
    """
    ✅ MMR 순위를 기반으로 2 to 1 (1/2, 3/4, 5/6, 7/8) 로 팀을 나눔 (고급 모드)
    ✅ 닉네임 지원 및 포지션 무작위 섞기 적용
    """
    import random
    logging.info("🚀 [팀생성고급] 명령어 실행됨")

    # ✅ 유저 입력 받기
    if not players:
        await ctx.send(
            "※ **해당 명령어는 관리자 전용 입니다.**\n"
            "일반적인 팀생성은 `!팀생성` 명령어를 사용해주세요.\n"
            "📌 **팀을 생성할 유저 목록을 입력하세요!** (쉼표 또는 슬래시 구분, 정확히 8명 입력 필수)"
        )
        try:
            msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
            players = msg.content.strip()
        except asyncio.TimeoutError:
            await ctx.send("⏳ **시간 초과! 다시 `!팀생성고급` 명령어를 입력하세요.**")
            return

    player_list = list(set(re.split(r"[,/]", players.strip())))
    logging.info(f"🎯 입력된 유저 리스트: {player_list}")

    # ✅ GAS에서 등록된 유저 및 별명 목록 가져오기
    alias_response = requests.get(f"{GAS_URL}?action=getUsersAndAliases")
    try:
        alias_data = alias_response.json()
        existing_users = alias_data.get("users", [])
        existing_aliases = alias_data.get("aliases", {})
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{alias_response.text}`")
        return

    # ✅ 닉네임 → 실제 유저명 변환
    resolved_players = []
    unresolved_players = []

    for player in player_list:
        if player in existing_users:
            resolved_players.append(player)  # ✅ 유저명이 존재하면 그대로 추가
        else:
            matched_user = None
            for username, aliases in existing_aliases.items():
                if player in aliases:
                    matched_user = username
                    break
            if matched_user:
                resolved_players.append(matched_user)  # ✅ 닉네임을 유저명으로 변환하여 추가
                logging.info(f"🔄 닉네임 `{player}` → 유저명 `{matched_user}` 변환 완료")
            else:
                unresolved_players.append(player)  # ✅ 등록되지 않은 유저 저장

    logging.info(f"✅ 최종 변환된 유저 리스트: {resolved_players}")
    logging.info(f"🚨 등록되지 않은 유저: {unresolved_players}")

    # ✅ 등록되지 않은 유저가 있으면 팀 생성 불가
    if unresolved_players:
        await ctx.send(
            f"🚨 **팀 생성 불가!** ❌\n"
            f"⛔ **등록되지 않은 유저/닉네임**: `{', '.join(unresolved_players)}`\n"
            "📌 **해결 방법**: `!등록 [유저명]` 명령어로 유저를 등록한 후 다시 시도해주세요!"
        )
        return

    # ✅ 유저 정보 요청 (GAS)
    payload = {"action": "getPlayersInfo", "players": resolved_players}
    response = requests.post(GAS_URL, json=payload)

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    if "error" in data:
        await ctx.send(f"🚨 {data['error']}")
        return

    players_data = data["players"]

    # ✅ MMR 기준 정렬 (내림차순)
    players_data.sort(key=lambda x: x['mmr'], reverse=True)
    logging.info(f"📊 MMR 정렬된 유저 리스트: {[(p['username'], p['mmr']) for p in players_data]}")

    # ✅ MMR 순위에 따른 고정 팀 배정 (2 to 1)
    possible_combinations = [
        ([0, 2, 4, 6], [1, 3, 5, 7]),
        ([0, 3, 5, 6], [1, 2, 4, 7]),
        ([0, 2, 5, 7], [1, 3, 4, 6]),
        ([0, 3, 4, 7], [1, 2, 5, 6])
    ]

    # ✅ 랜덤하게 팀 조합을 선택 (최대 10번 시도)
    attempts = 0
    valid_teams = False
    team1, team2 = [], []

    while attempts < 10 and possible_combinations:
        team1_idx, team2_idx = random.choice(possible_combinations)
        team1 = [players_data[i] for i in team1_idx]
        team2 = [players_data[i] for i in team2_idx]
        logging.info(f"🎲 랜덤 팀 배정 시도 {attempts+1}: 팀1 - {team1}, 팀2 - {team2}")

        valid_teams = True  # 필요하면 check_valid_teams 추가 가능
        if valid_teams:
            break
        attempts += 1

    if not valid_teams:
        await ctx.send("🚨 **팀 생성 실패! 유효한 조합을 찾을 수 없습니다.**")
        return

    # ✅ 팀 내 포지션 랜덤 배치
    def shuffle_team_roles(team):
        positions = ["드", "어", "넥", "슴"]
        random.shuffle(positions)
        shuffled_team = []

        for position in positions:
            available_players = [p for p in team if position in p["class"]]
            if available_players:
                selected_player = random.choice(available_players)
                shuffled_team.append({"username": selected_player["username"], "class": position})
                team.remove(selected_player)

        return shuffled_team

    team1 = shuffle_team_roles(team1)
    team2 = shuffle_team_roles(team2)

    logging.info(f"🔄 팀1 최종 포지션: {team1}")
    logging.info(f"🔄 팀2 최종 포지션: {team2}")

    # ✅ 최종 팀 배정 후 메시지 출력
    team1_names = "/".join([p['username'] for p in team1])
    team2_names = "/".join([p['username'] for p in team2])
    msg = f"[아래] {team1_names} vs [위] {team2_names}"

    await ctx.send(msg)


@bot.command()
async def MMR갱신(ctx):
    """
    ✅ 모든 플레이어의 MMR을 현재 계수 정보로 다시 계산하는 명령어
    ✅ 디버깅 로그 추가됨 (요청 시작, 응답 확인, 오류 처리)
    """
    import logging

    logging.info("🚀 [MMR갱신] 명령어 실행됨")

    await ctx.send("🔄 **모든 플레이어의 MMR을 최신 계수 값으로 갱신 중입니다... (잠시만 기다려주세요!)**")

    payload = {"action": "updateAllMMR"}
    logging.info(f"📤 [MMR갱신 요청] Payload: {payload}")

    response = requests.post(GAS_URL, json=payload)

    try:
        data = response.json()
        logging.info(f"📩 [서버 응답 수신] 응답 데이터: {data}")

    except requests.exceptions.JSONDecodeError:
        logging.error(f"🚨 [오류] GAS 응답이 JSON 형식이 아님! 응답 내용: {response.text}")
        await ctx.send(f"🚨 **오류 발생:** GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    # ✅ 서버 응답 확인
    if "error" in data:
        logging.error(f"🚨 [오류] MMR 갱신 중 문제 발생: {data['error']}")
        await ctx.send(f"🚨 **MMR 갱신 실패!**\n🔍 오류 내용: `{data['error']}`")
        return

    # ✅ 성공적으로 갱신된 경우
    logging.info("✅ [MMR갱신 완료] 모든 플레이어의 MMR이 정상적으로 갱신됨")
    await ctx.send(f"✅ **모든 플레이어의 MMR이 갱신되었습니다!**")

@bot.command()
async def 별명삭제(ctx, username: str = None):
    """
    ✅ 특정 유저의 모든 등록된 별명을 삭제하는 명령어
    - `!별명삭제 유저명` → 해당 유저의 별명을 삭제
    - `!별명삭제` → 유저명을 입력받아서 별명을 삭제
    ✅ 디버깅 로그 추가됨
    """
    import logging
    logging.basicConfig(level=logging.INFO)

    logging.info("🚀 [별명삭제] 명령어 실행됨")

    # ✅ GAS에서 유저별 별명 가져오기
    def get_existing_users_and_aliases():
        try:
            logging.info("🔍 GAS에서 기존 유저 및 별명 데이터를 가져오는 중...")
            response = requests.get(f"{GAS_URL}?action=getUsersAndAliases")

            if response.status_code == 200:
                data = response.json()
                logging.info("✅ GAS 유저 및 별명 데이터 가져오기 성공!")
                return data.get("users", []), data.get("aliases", {})

            else:
                logging.warning(f"⚠ GAS 데이터 가져오기 실패! HTTP {response.status_code}")
                return [], {}

        except Exception as e:
            logging.error(f"🚨 [오류] GAS 요청 중 문제 발생: {e}")
            return [], {}

    # ✅ 유저 및 별명 데이터 가져오기
    existing_users, existing_aliases = get_existing_users_and_aliases()
    logging.info(f"📋 [유저 목록] 기존 등록된 유저명: {existing_users}")
    logging.info(f"📋 [별명 목록] 기존 등록된 별명: {existing_aliases}")

    # ✅ 대화형 모드: 유저명을 입력받기
    if username is None:
        await ctx.send("🎮 **별명을 삭제할 유저명을 입력하세요! (30초 내 입력)**")

        try:
            msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
            username = msg.content.strip()
            logging.info(f"✅ [입력 받은 유저명] {username}")

        except asyncio.TimeoutError:
            logging.warning("⏳ [시간 초과] 별명 삭제 요청이 중단됨")
            await ctx.send("⏳ **시간 초과! 다시 `!별명삭제` 명령어를 입력하세요.**")
            return

    # ✅ 유저 존재 여부 확인
    if username not in existing_users:
        logging.warning(f"🚨 [오류] `{username}` 유저가 등록되지 않음")
        await ctx.send(f"🚨 **유저 `{username}` 를 찾을 수 없습니다!** 먼저 `!등록` 명령어로 등록하세요.")
        return

    # ✅ 해당 유저의 별명 확인
    user_aliases = existing_aliases.get(username, [])
    logging.info(f"📋 `{username}` 님의 현재 등록된 별명: {user_aliases}")

    if not user_aliases:
        logging.info(f"⚠️ `{username}` 님은 별명이 등록되어 있지 않음")
        await ctx.send(f"⚠️ **`{username}` 님은 등록된 별명이 없습니다!**")
        return

    # ✅ 삭제 요청 확인 메시지
    confirm_msg = (
        f"⚠️ **`{username}` 님의 모든 별명을 삭제하시겠습니까?**\n"
        f"📋 **현재 등록된 별명:** `{', '.join(user_aliases)}`"
    )
    error_msg = "🚨 별명 삭제 요청에 실패했습니다."

    # ✅ GAS로 삭제 요청 준비
    payload = {
        "action": "deleteAlias",
        "username": username
    }
    logging.info(f"📤 [별명 삭제 요청] Payload: {payload}")

    # ✅ 삭제 요청을 확인하는 ConfirmView 생성
    view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 별명이 삭제되었습니다!", error_msg)
    await ctx.send(confirm_msg, view=view)
    logging.info(f"✅ [별명 삭제 요청 전송 완료] `{username}` 님의 별명 삭제 요청됨")

@bot.command(aliases=["홈피", "웹페이지", "웹"])
async def 홈페이지(ctx):
    """전적 기록실 웹페이지로 이동하는 버튼 제공"""
    view = discord.ui.View()
    button = discord.ui.Button(label="📊 [전적 기록실 이동]", url="https://my-d2-league.vercel.app/", style=discord.ButtonStyle.link)
    view.add_item(button)

    await ctx.send("🔗 **전적 기록실 웹페이지로 이동하려면 버튼을 클릭해주세요.**", view=view)


@bot.command(aliases=["셋팅"])
async def 세팅(ctx):
    """캐릭터별 세팅을 볼 수 있는 블로그 링크 버튼 제공"""
    view = discord.ui.View()
    button = discord.ui.Button(label="🔧 [클래스별 세팅가이드]", url="https://blog.naver.com/lovlince/222991937440",
                               style=discord.ButtonStyle.link)
    view.add_item(button)

    await ctx.send("🔗 **각 클래스별 세팅을 조회하시려면, 아래 버튼을 클릭해주세요.**", view=view)

import aiohttp

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class TeamGenerationView(discord.ui.View):
    def __init__(self, ctx, players):
        super().__init__()
        self.ctx = ctx
        self.players = players
        self.team1 = []
        self.team2 = []
        self.message = None  # ✅ 기존 메시지를 저장할 변수 추가
        self.status_message = None  # ✅ "팀 생성 중..." 메시지 저장 변수

    async def get_player_data(self):
        """GAS에서 유저 정보 가져오기 (비동기 방식)"""
        payload = {"action": "getPlayersInfo", "players": self.players}
        logging.info(f"📡 [GAS 요청] 유저 정보 요청: {payload}")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(GAS_URL, json=payload, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        logging.info(f"✅ [GAS 응답] 성공: {data}")
                        return data
                    else:
                        logging.warning(f"⚠ [GAS 응답] 실패 (상태 코드: {response.status})")
                        await self.ctx.send(f"🚨 GAS 응답 오류: 상태 코드 {response.status}")
                        return None
            except Exception as e:
                logging.error(f"🚨 GAS 요청 실패: {e}")
                await self.ctx.send(f"🚨 GAS 요청 중 오류 발생: {e}")
                return None

    def generate_teams(self, players_data):
        """MMR 기반 팀 생성 (일반 방식)"""
        players_data.sort(key=lambda x: x["mmr"], reverse=True)  # MMR 정렬
        logging.info(f"📊 [MMR 정렬] 유저 데이터: {[(p['username'], p['mmr']) for p in players_data]}")

        top_half = random.sample(players_data[:4], 2)
        bottom_half = random.sample(players_data[4:], 2)
        self.team1 = top_half + bottom_half
        self.team2 = [p for p in players_data if p not in self.team1]

        logging.info(f"🔴 [팀1] {self.team1}")
        logging.info(f"🔵 [팀2] {self.team2}")

    def generate_teams_advanced(self, players_data):
        """MMR 기반 팀 생성 (고급 방식)"""
        players_data.sort(key=lambda x: x["mmr"], reverse=True)
        logging.info(f"📊 [고급 MMR 정렬] 유저 데이터: {[(p['username'], p['mmr']) for p in players_data]}")

        possible_combinations = [
            ([0, 2, 4, 6], [1, 3, 5, 7]),
            ([0, 3, 5, 6], [1, 2, 4, 7]),
            ([0, 2, 5, 7], [1, 3, 4, 6]),
            ([0, 3, 4, 7], [1, 2, 5, 6])
        ]

        attempts = 0
        while attempts < 10:
            team1_idx, team2_idx = random.choice(possible_combinations)
            self.team1 = [players_data[i] for i in team1_idx]
            self.team2 = [players_data[i] for i in team2_idx]

            logging.info(f"🎲 [고급 랜덤 배정 시도 {attempts + 1}] 팀1: {self.team1}, 팀2: {self.team2}")
            return

        logging.warning("🚨 [고급 팀 생성 실패] 유효한 조합을 찾지 못함")
        self.ctx.send("🚨 **팀 생성 실패! 유효한 조합을 찾을 수 없습니다.**")

    @discord.ui.button(label="MIX!", style=discord.ButtonStyle.green)
    async def mix_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        """일반 MMR 기반 팀 생성"""
        await interaction.response.defer()
        self.disable_buttons()  # ✅ 버튼 비활성화
        await self.update_status_message("⏳ **팀을 생성 중입니다...**")  # ✅ "팀 생성 중..." 메시지 표시

        data = await self.get_player_data()
        if not data or "players" not in data:
            self.enable_buttons()  # ✅ 서버 응답 실패 시 버튼 다시 활성화
            return

        self.generate_teams(data["players"])

        result_msg = f"""🏆 **MMR 기반 팀 생성 결과 (일반)** 🏆

        🔴 **아랫팀:** {', '.join([p['username'] for p in self.team1])}
        🔵 **윗팀:** {', '.join([p['username'] for p in self.team2])}

        🎮 경기 준비 완료!"""

        await self.update_status_message(result_msg)  # ✅ 기존 메시지 업데이트

        self.enable_buttons()  # ✅ 서버 응답 완료 후 버튼 다시 활성화

    @discord.ui.button(label="MIX!(고급)", style=discord.ButtonStyle.blurple)
    async def mix_teams_advanced(self, interaction: discord.Interaction, button: discord.ui.Button):
        """고급 MMR 기반 팀 생성"""
        await interaction.response.defer()
        await self.update_status_message("⏳ **팀(고급)을 생성 중입니다...**")  # ✅ "팀 생성 중..." 메시지 표시
        self.disable_buttons()  # ✅ 버튼 비활성화

        data = await self.get_player_data()
        if not data or "players" not in data:
            self.enable_buttons()  # ✅ 서버 응답 실패 시 버튼 다시 활성화
            return

        self.generate_teams_advanced(data["players"])

        result_msg = f"""🏆 **MMR 기반 팀 생성 결과 (고급)** 🏆

        🔴 **아랫팀:** {', '.join([p['username'] for p in self.team1])}
        🔵 **윗팀:** {', '.join([p['username'] for p in self.team2])}

        🎮 경기 준비 완료!"""
        await self.update_status_message(result_msg)  # ✅ 기존 메시지 업데이트

        self.enable_buttons()  # ✅ 서버 응답 완료 후 버튼 다시 활성화

    @discord.ui.button(label="생성결과 복사", style=discord.ButtonStyle.gray)
    async def copy_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        """생성된 팀 결과를 복사"""
        if not self.team1 or not self.team2:
            await interaction.response.send_message("❌ **MIX 버튼을 눌러 팀을 먼저 생성하세요!**", ephemeral=True)
            return

        try:
            result_text = f"[아래]{'/'.join([p['username'] for p in self.team1])} vs [위]{'/'.join([p['username'] for p in self.team2])}"
            await interaction.response.send_message(f"📋 **생성 결과가 복사되었습니다!**\n```{result_text}```", ephemeral=True)
        except Exception as e:
            logging.error(f"🚨 [복사 오류] {e}")
            await interaction.response.send_message(f"🚨 오류 발생: {e}", ephemeral=True)

    def disable_buttons(self):
        """버튼을 비활성화 (서버 응답 대기 중)"""
        for child in self.children:
            child.disabled = True
        if self.message:
            asyncio.create_task(self.message.edit(view=self))

    def enable_buttons(self):
        """버튼을 다시 활성화 (서버 응답 완료 후)"""
        for child in self.children:
            child.disabled = False
        if self.message:
            asyncio.create_task(self.message.edit(view=self))

    async def update_status_message(self, content):
        """상태 메시지 업데이트 (팀 생성 중 → 결과 표시)"""
        if self.status_message:
            await self.status_message.edit(content=content)
        else:
            self.status_message = await self.ctx.send(content)


@bot.command()
async def 팀생성(ctx, *, players: str = None):
    """팀 생성 명령어"""
    logging.info(f"🚀 [팀생성 명령어 실행] 입력된 플레이어: {players}")

    if not players:
        await ctx.send("🚨 **8명의 유저를 입력하세요! (쉼표 또는 슬래시로 구분)**")
        return

    player_list = list(set(re.split(r"[,/]", players.strip())))
    if len(player_list) != 8:
        await ctx.send("🚨 **정확히 8명의 유저를 입력해야 합니다!**")
        return

    view = TeamGenerationView(ctx, player_list)
    message = await ctx.send("🔄 **팀을 생성할 방식을 선택하세요!**", view=view)
    view.message = message  # ✅ 첫 번째 메시지를 저장하여 이후 MIX 버튼 클릭 시 업데이트 가능

bot.run(TOKEN)
