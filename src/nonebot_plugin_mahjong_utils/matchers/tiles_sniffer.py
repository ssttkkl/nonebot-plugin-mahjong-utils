import re
from io import StringIO

from mahjong_utils.hora import build_hora_from_shanten_result
from mahjong_utils.models.furo import Furo
from mahjong_utils.models.tile import parse_tiles, Tile
from mahjong_utils.shanten import shanten
from nonebot import on_regex, Bot
from nonebot.internal.adapter import Event
from nonebot.internal.matcher import Matcher
from nonebot.typing import T_State

from nonebot_plugin_mahjong_utils.errors import BadRequestError
from nonebot_plugin_mahjong_utils.interceptors.handle_error import handle_error
from nonebot_plugin_mahjong_utils.utils.executor import run_in_my_executor
from nonebot_plugin_mahjong_utils.utils.mapper import map_shanten_result, map_hora
from nonebot_plugin_mahjong_utils.utils.parser import try_parse_wind, try_parse_extra_yaku

tiles_pattern = r"([0-9]+(m|p|s|z){1})+"
furo_pattern = r"[0-9]+(m|p|s|z){1}"

tiles_sniffer = on_regex(rf"^{tiles_pattern}(\s{furo_pattern})*(\s.*)*$")


def to_msg(tiles, got, furo, dora, self_wind, round_wind, extra_yaku):
    tiles = [Tile.by_type_and_num(x.tile_type, x.real_num) for x in tiles]
    if got is not None:
        got = Tile.by_type_and_num(got.tile_type, got.real_num)

    result = shanten(tiles, furo)
    with StringIO() as sio:
        if result.shanten == -1 and len(result.hand.furo) * 3 + len(tiles) == 14:
            # 分析和牌
            hora_ron = build_hora_from_shanten_result(
                result, tiles[-1], False,
                dora=dora, self_wind=self_wind, round_wind=round_wind,
                extra_yaku=extra_yaku
            )
            hora_tsumo = build_hora_from_shanten_result(
                result, tiles[-1], True,
                dora=dora, self_wind=self_wind, round_wind=round_wind,
                extra_yaku=extra_yaku
            )
            map_hora(sio, hora_ron, hora_tsumo, got=got)
        else:
            map_shanten_result(sio, result, got=got)

        msg = sio.getvalue().strip()
        return msg


@tiles_sniffer.handle()
@handle_error(tiles_sniffer, True)
async def handle(bot: Bot, event: Event, state: T_State, matcher: Matcher):
    text = event.get_plaintext().split(' ')

    tiles = parse_tiles(text[0])
    furo = []
    tsumo = False
    dora = 0
    self_wind = None
    round_wind = None
    extra_yaku = set()

    for t in text[1:]:
        if re.match(furo_pattern, t):
            furo.append(Furo.parse(t))
        elif len(t) > 4 and t[:4].lower() == "dora":
            dora = int(t[len("dora"):])
        elif t.startswith("自风"):
            if self_wind is None:
                self_wind = try_parse_wind(t[len("自风"):])
        elif t.endswith("家"):
            if self_wind is None:
                self_wind = try_parse_wind(t[:len("家")])
        elif t.startswith("场风"):
            if round_wind is None:
                round_wind = try_parse_wind(t[len("场风"):])
        else:
            yaku = try_parse_extra_yaku(t)
            if yaku is not None:
                extra_yaku.add(yaku)

    if len(tiles) % 3 == 0:
        raise BadRequestError(f"invalid length of hand: {len(tiles)}")

    if len(tiles) % 3 == 2:
        got = tiles[-1]
    else:
        got = None

    if len(furo) == 0 and len(tiles) < 3:
        # 少于三张牌不进行计算
        return

    msg = await run_in_my_executor(to_msg, tiles, got, furo, dora, self_wind, round_wind, extra_yaku)
    await matcher.send(msg)
