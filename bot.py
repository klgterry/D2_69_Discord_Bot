import discord
from discord.ext import commands
import requests
import datetime
import json
import random
import asyncio
import re

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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author  # 명령어 입력한 유저만 조작 가능

    async def send_followup(self, interaction: discord.Interaction, message: str):
        """✅ 처리 중 메시지 전송"""
        return await interaction.followup.send(f"⌛ {message} 잠시만 기다려주세요!")

    def extract_game_number(self, response_text: str) -> str:
        """✅ GAS 응답에서 게임번호 추출 (JSON or 정규식)"""
        try:
            data = json.loads(response_text.strip().strip('"'))
            return data.get("game_number", "알 수 없음")
        except json.JSONDecodeError:
            match = re.search(r"게임번호:\s*(\d+)", response_text)
            return match.group(1) if match else "알 수 없음"

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        followup_message = await self.send_followup(interaction, "처리 중입니다.")

        try:
            response = await asyncio.to_thread(requests.post, GAS_URL, json=self.payload)

            # ✅ 디버깅: 응답 상태 코드와 내용 출력
            print(f"🚀 요청 데이터: {self.payload}")  # 🔥 요청 내용 확인
            print(f"🚀 응답 코드: {response.status_code}")  # 🔥 응답 코드 확인
            print(f"🚀 응답 본문: {response.text}")  # 🔥 응답 내용 확인

            if response.status_code != 200:
                raise requests.HTTPError(f"응답 코드 {response.status_code}")

            response_text = response.text.strip().strip('"')



            # ✅ "game_result" 타입인 경우, 경기번호를 포함한 메시지 생성
            if self.payload_type == "game_result":
                game_number = self.extract_game_number(response_text)
                message = self.success_message(game_number) if callable(self.success_message) else self.success_message
            else:
                message = self.success_message  # 일반적인 명령어 처리

            await followup_message.edit(content=message)

        except (requests.RequestException, Exception) as e:
            await followup_message.edit(content=f"🚨 {self.error_message}\n오류: {str(e)}")

        self.stop()

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🚫 작업이 취소되었습니다.", ephemeral=True)
        self.stop()

@bot.event
async def on_ready():
    print(f'✅ {bot.user}로 로그인 완료!')


@bot.command()
async def 등록(ctx, username: str = None):
    if username:
        payload = {"action": "register", "username": username}
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님이 등록되었습니다!", "🚨 등록 요청에 실패했습니다.")

        await ctx.send(f"📋 `{username}` 님을 등록하시겠습니까?", view=view)
        return

    # 유저명을 입력받는 대화형 모드
    await ctx.send("🎮 등록할 유저명을 입력하세요! (30초 내 입력)")

    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        username = msg.content.strip()

        payload = {"action": "register", "username": username}
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님이 등록되었습니다!", "🚨 등록 요청에 실패했습니다.")

        await ctx.send(f"📋 `{username}` 님을 등록하시겠습니까?", view=view)

    except:
        await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!등록`을 입력하세요!")

@bot.command()
async def 별명등록(ctx, username: str = None, *, aliases: str = None):
    if username and aliases:
        alias_list = [alias.strip() for alias in aliases.split(",")]  # 쉼표로 별명 분리
        payload = {
            "action": "registerAlias",
            "username": username,
            "aliases": alias_list
        }
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 별명이 등록되었습니다: {', '.join(alias_list)}", "🚨 별명 등록 요청에 실패했습니다.")

        await ctx.send(f"📋 `{username}` 님의 별명을 `{', '.join(alias_list)}` (으)로 등록하시겠습니까?", view=view)
        return

    # 유저명을 입력받는 대화형 모드
    await ctx.send("🎮 별명을 등록할 유저명을 입력하세요! (30초 내 입력)")

    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        username = msg.content.strip()

        await ctx.send(f"✏️ `{username}` 님의 별명을 입력하세요! (쉼표로 구분, 30초 내 입력)")

        msg = await bot.wait_for("message", check=check, timeout=30.0)
        alias_list = [alias.strip() for alias in msg.content.split(",")]

        payload = {
            "action": "registerAlias",
            "username": username,
            "aliases": alias_list
        }
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 별명이 등록되었습니다: {', '.join(alias_list)}", "🚨 별명 등록 요청에 실패했습니다.")

        await ctx.send(f"📋 `{username}` 님의 별명을 `{', '.join(alias_list)}` (으)로 등록하시겠습니까?", view=view)

    except:
        await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!별명등록`을 입력하세요!")

@bot.command()
async def 삭제(ctx, username: str = None):
    if username:
        payload = {"action": "deleteUser", "username": username}
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 정보가 삭제되었습니다!", "🚨 삭제 요청에 실패했습니다.")

        await ctx.send(f"⚠️ `{username}` 님의 정보를 삭제하시겠습니까?", view=view)
        return

    # 대화형 모드
    await ctx.send("🗑 삭제할 유저명을 입력하세요! (30초 내 입력)")

    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        username = msg.content.strip()

        payload = {"action": "deleteUser", "username": username}
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 정보가 삭제되었습니다!", "🚨 삭제 요청에 실패했습니다.")

        await ctx.send(f"⚠️ `{username}` 님의 정보를 삭제하시겠습니까?", view=view)

    except:
        await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!삭제`를 입력하세요!")

@bot.command()
async def 조회(ctx, username: str = None):
    """
    ✅ 새로운 Results 시트 구조 반영
    """
    if not username:
        await ctx.send("🔍 조회할 유저명을 입력하세요! 예시: `!조회 규석문`")
        return

    response = requests.post(GAS_URL, json={"action": "getUserInfo", "username": username})
    raw_response = response.text  # 🔍 원본 응답 저장 (디버깅 용도)

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{raw_response}`")
        return

    if "error" in data:
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

    await ctx.send(msg)


@bot.command()
async def 클래스(ctx, username: str = None, *, classes: str = None):
    if username and classes:
        class_list = [c.strip() for c in classes.split(",")]
        payload = {
            "action": "registerClass",
            "username": username,
            "classes": class_list
        }
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 클래스가 등록되었습니다: {', '.join(class_list)}", "🚨 클래스 등록 요청에 실패했습니다.")

        await ctx.send(f"🛡 `{username}` 님의 클래스를 `{', '.join(class_list)}` (으)로 등록하시겠습니까?", view=view)
        return

    # 대화형 모드
    await ctx.send("🎭 클래스를 등록할 유저명을 입력하세요! (30초 내 입력)")

    try:
        msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
        username = msg.content.strip()

        await ctx.send(f"🛡 `{username}` 님의 클래스를 입력하세요! (쉼표로 구분(예시 : 드,어,넥,슴), 30초 내 입력)")

        msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=30.0)
        class_list = [c.strip() for c in msg.content.split(",")]

        payload = {
            "action": "registerClass",
            "username": username,
            "classes": class_list
        }
        view = ConfirmView(ctx, payload, f"✅ `{username}` 님의 클래스가 등록되었습니다: {', '.join(class_list)}", "🚨 클래스 등록 요청에 실패했습니다.")

        await ctx.send(f"🛡 `{username}` 님의 클래스를 `{', '.join(class_list)}` (으)로 등록하시겠습니까?", view=view)

    except:
        await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!클래스`를 입력하세요!")

import discord
import requests
import re

@bot.command()
async def 결과등록(ctx, *, input_text: str = None):
    """
    !결과등록 명령어: 승리팀과 패배팀을 입력하면 경기 결과를 등록
    """
    if input_text:
        # ✅ 즉시 등록 모드 (명령어 입력 시 바로 실행)
        win_players, lose_players = parse_match_input(input_text)
        if win_players is None or lose_players is None:
            await ctx.send(
                "🚨 **잘못된 형식입니다!**\n"
                "`!결과등록 [승]유저1,유저2,유저3,유저4[패]유저5,유저6,유저7,유저8`\n"
                "✅ **순서 주의:** 반드시 `드,어,넥,슴` 클래스 순서대로 입력해야 합니다."
            )
            return
        await validate_and_register(ctx, win_players, lose_players)
        return

    # ✅ 대화형 입력 모드 (설명을 보여주고 입력을 유도)
    await ctx.send(
        "🏆 **경기 결과를 입력하세요!**\n"
        "예시: `!결과등록 [승]유저1,유저2,유저3,유저4[패]유저5,유저6,유저7,유저8`\n"
        "✅ **순서 주의:** 반드시 `드,어,넥,슴` 클래스 순서대로 입력해야 합니다."
    )


async def validate_and_register(ctx, win_players, lose_players):
    """
    유저 등록 여부 확인 후 경기 등록 진행 (중복 등록 방지)
    """
    if len(win_players) != 4 or len(lose_players) != 4:
        await ctx.send(
            "🚨 **잘못된 입력입니다!**\n"
            "승리팀 혹은 패배팀의 인원 수 (4명) 를 확인해주세요.\n\n"
            "🔹 **올바른 입력 예시:** `!결과등록 [승]유저1,유저2,유저3,유저4[패]유저5,유저6,유저7,유저8`"
        )
        return

    all_players = win_players + lose_players
    response = requests.post(GAS_URL, json={"action": "getPlayersInfo", "players": all_players})

    if response.status_code != 200:
        await ctx.send("🚨 서버 응답 오류로 인해 경기 등록을 진행할 수 없습니다. 다시 시도해주세요.")
        return

    data = response.json()

    if "error" in data:
        await ctx.send(f"🚨 {data['error']}")
        return

    registered_users = {player["username"] for player in data["players"]}
    unregistered_users = [p for p in all_players if p not in registered_users]

    if unregistered_users:
        await ctx.send(f"🚨 등록되지 않은 유저가 포함되어 있습니다: {', '.join(unregistered_users)}")
        return

    # ✅ 경기번호 생성 (YYMMDDHHMM 형식)
    from datetime import datetime
    game_number = datetime.now().strftime("%y%m%d%H%M")

    # ✅ 모든 유저가 등록된 경우에만 `ConfirmView`로 진행
    payload = {
        "action": "registerResult",
        "game_number": game_number,
        "winners": win_players,
        "losers": lose_players
    }

    view = ConfirmView(
        ctx,
        payload,
        lambda x: f"✅ 경기 결과가 기록되었습니다! **[게임번호: {x}]**\n"
                  f" - 등록 [승] {format_team(win_players)}\n"
                  f" - 등록 [패] {format_team(lose_players)}",
        "🚨 경기 등록 요청에 실패했습니다.",
        payload_type="game_result",
        game_number=game_number
    )

    await ctx.send(
        f"📊 **승리 팀:** {format_team(win_players)}\n"
        f"❌ **패배 팀:** {format_team(lose_players)}\n\n"
        f"경기 결과를 등록하시겠습니까?",
        view=view
    )


def parse_match_input(input_text):
    """
    경기 결과 텍스트에서 승리/패배 팀을 추출하는 함수
    """
    match = re.match(r"\[승\](.+?)\[패\](.+)", input_text)
    if not match:
        return None, None

    win_players = [p.strip() for p in match.group(1).split(",")]
    lose_players = [p.strip() for p in match.group(2).split(",")]

    return win_players, lose_players


def format_team(team):
    """
    유저명 + 클래스 (드, 어, 넥, 슴) 포맷 적용
    """
    class_order = ["드", "어", "넥", "슴"]
    return ", ".join(f"{player}({class_order[i]})" for i, player in enumerate(team))


@bot.command()
async def 결과조회(ctx, game_number: str = None):
    # 특정 경기 조회 or 최근 경기 조회
    if game_number:
        payload = {"action": "getMatch", "game_number": int(game_number)}
    else:
        payload = {"action": "getRecentMatches"}

    print(f"🚀 요청 URL: {GAS_URL}")
    print(f"📡 전송 데이터: {payload}")

    response = requests.post(GAS_URL, json=payload)

    try:
        data = response.json()
        print(f"🔍 변환된 GAS 응답 (JSON): {json.dumps(data, indent=2, ensure_ascii=False)}")  # ✅ JSON 데이터 디버깅
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    # ✅ 최근 5경기 조회
    if "matches" in data and len(data["matches"]) > 0:
        msg = "📊 **최근 5경기 결과:**\n"
        for i, match in enumerate(data["matches"], start=1):
            print(f"🧐 디버깅: match 데이터 = {match}")  # ✅ match 데이터 확인

            # 날짜 포맷 변경
            timestamp = match["timestamp"]
            try:
                formatted_date = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
            except ValueError:
                formatted_date = timestamp  # 변환 실패 시 원래 값 사용

            msg += f"`[{i}]` 🎮 **게임번호:** `{match['game_number']}`\n"
            msg += f"📅 **날짜:** {formatted_date}\n"
            msg += f"🏆 **승리 팀:** {match['winners']}\n"
            msg += f"❌ **패배 팀:** {match['losers']}\n\n"
        await ctx.send(msg)

    # ✅ 특정 경기 조회
    elif "game_number" in data:
        print("✅ 개별 경기 데이터가 감지됨!")  # ✅ 디버깅 로그 추가
        msg = f"📜 **경기 정보**\n"
        msg += f"🎮 **게임번호:** `{data['game_number']}`\n"
        msg += f"📅 **날짜:** {data['timestamp']}\n"
        msg += f"🏆 **승리 팀:** {data['winners']}\n"
        msg += f"❌ **패배 팀:** {data['losers']}"
        await ctx.send(msg)

    else:
        await ctx.send("🚨 해당 경기 기록이 없습니다.")


@bot.command()
async def 결과삭제(ctx, game_number: str = None):
    if not game_number:
        await ctx.send("🗑 삭제할 경기번호를 입력하세요! (30초 내 입력)")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            game_number = msg.content.strip()  # 사용자가 입력한 게임번호
        except:
            await ctx.send("⏳ 시간이 초과되었습니다. 다시 `!결과삭제`를 입력하세요!")
            return

    # ✅ 해당 경기의 정보를 먼저 조회
    response = requests.post(GAS_URL, json={"action": "getMatch", "game_number": game_number})

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    if "error" in data:
        await ctx.send(f"🚨 {data['error']}")
        return

    # ✅ 승/패 팀 정보 가져오기 (리스트로 변환)
    win_players = data.get("winners", "").split(", ") if isinstance(data.get("winners"), str) else data.get("winners",
                                                                                                            [])
    lose_players = data.get("losers", "").split(", ") if isinstance(data.get("losers"), str) else data.get("losers", [])

    # ✅ 팀 데이터가 정상적으로 로드되었는지 확인
    print(f"DEBUG - 승리 팀: {win_players}")
    print(f"DEBUG - 패배 팀: {lose_players}")

    def format_team(team):
        """ 유저명 + 클래스 순서 적용 """
        if not team or len(team) < 4:
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

    # ✅ 삭제 요청 전 확인
    payload = {"action": "deleteMatch", "game_number": game_number}

    async def confirm_callback(interaction):
        response = requests.post(GAS_URL, json=payload)
        try:
            data = response.json()
            if "error" in data:
                await ctx.send(f"🚨 오류: {data['error']}")
                return

            # ✅ 삭제 완료 메시지 (경기 정보 포함)
            result_message = (
                f"✅ `{game_number}` 경기 기록이 삭제되었습니다!\n"
                f" - 삭제 [승] {win_team_info}\n"
                f" - 삭제 [패] {lose_team_info}"
            )
            await ctx.send(result_message)

        except Exception as e:
            await ctx.send("🚨 경기 삭제 요청에 실패했습니다.")

    result_message = (
        f"✅ `{game_number}` 경기 기록이 삭제되었습니다!\n"
        f" - 삭제 [승] {win_team_info}\n"
        f" - 삭제 [패] {lose_team_info}"
    )

    view = ConfirmView(
        ctx,
        payload,
        result_message,
        "경기 삭제 요청에 실패했습니다.",
        payload_type="game_result",
        game_number=game_number)

    await ctx.send(delete_message, view=view)


@bot.command(aliases=["도움", "헬프", "명령어"])
async def 도움말(ctx):
    help_text = (
        "**📜 사용 가능한 명령어 목록:**\n"
        "```yaml\n"
        "!등록 [유저명] - 유저 등록\n"
        "!별명등록 [유저명] [별명1, 별명2, ...] - 유저 별명 추가\n"
        "!삭제 [유저명] - 유저 삭제\n"
        "!조회 [유저명] - 유저 정보 조회\n"
        "!클래스 [유저명] [클래스명] - 유저 클래스 등록\n"
        "!결과등록 승 [유저1, 유저2, ...] / 패 [유저3, 유저4, ...] - 경기 결과 등록\n"
        "!결과조회 [게임번호] - 경기 결과 조회\n"
        "!결과삭제 [게임번호] - 경기 기록 삭제\n"
        "!팀생성 [유저1, 유저2, ...] - 자동 팀 생성\n"
        "!도움말 - 명령어 목록 확인\n"
        "```"
    )
    await ctx.send(help_text)

@bot.command()
async def 팀생성(ctx, *, players: str = None):
    """
    ✅ MMR 순위를 기반으로 1~4등 중 2명, 5~8등 중 2명을 뽑아 팀을 나눔
    """
    if not players:
        await ctx.send("🚨 팀을 생성할 유저 목록을 입력하세요! (쉼표로 구분, 정확히 8명 입력)")
        return

    player_list = [p.strip() for p in players.split(",")]

    if len(player_list) != 8:
        await ctx.send("🚨 정확히 8명의 유저를 입력하세요!")
        return

    payload = {"action": "getPlayersInfo", "players": player_list}
    response = requests.post(GAS_URL, json=payload)

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        await ctx.send(f"🚨 오류: GAS 응답이 JSON 형식이 아닙니다.\n🔍 응답 내용: `{response.text}`")
        return

    if "error" in data:
        await ctx.send(f"🚨 {data['error']}")
        return

    if "players" not in data:
        await ctx.send(f"🚨 오류: 유저 정보를 가져오지 못했습니다.\n🔍 응답 내용: `{data}`")
        return

    players_data = data["players"]
    registered_users = {p['username'] for p in players_data}
    missing_users = [p for p in player_list if p not in registered_users]

    if missing_users:
        await ctx.send(f"🚨 등록되지 않은 유저가 포함되어 있습니다: `{', '.join(missing_users)}`")
        return

    # ✅ MMR 기준 정렬 (내림차순)
    players_data.sort(key=lambda x: x['mmr'], reverse=True)

    # ✅ 팀을 나누는 함수
    def create_balanced_teams():
        # 1~4등 중 2명, 5~8등 중 2명씩 랜덤 선택
        top_half = random.sample(players_data[:4], 2)
        bottom_half = random.sample(players_data[4:], 2)

        team1 = top_half + bottom_half  # ✅ 팀1: 상위 4명 중 2명 + 하위 4명 중 2명
        team2 = [p for p in players_data if p not in team1]  # ✅ 나머지 4명이 팀2

        return team1, team2

    # ✅ 클래스 조합 검증
    def check_valid_teams(t1, t2):
        required_classes = {"드", "어", "넥", "슴"}
        team_classes = set()

        for player in t1 + t2:
            team_classes.update(player["class"].split(", "))

        return required_classes.issubset(team_classes)

    # ✅ 팀을 최대 10번 생성 시도 (클래스 조합이 유효한지 확인)
    attempts = 0
    valid_teams = False

    while attempts < 10:
        team1, team2 = create_balanced_teams()
        if check_valid_teams(team1, team2):
            valid_teams = True
            break
        attempts += 1

    if not valid_teams:
        await ctx.send("🚨 생성 불가능한 클래스 조합입니다. 다시 시도해주세요!")
        return

    # ✅ 팀 출력 형식 적용
    team1_names = "/".join([p['username'] for p in team1])
    team2_names = "/".join([p['username'] for p in team2])
    msg = f"[아래] {team1_names} vs [위] {team2_names}"

    await ctx.send(msg)


bot.run(TOKEN)
