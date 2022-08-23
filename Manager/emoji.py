from utils import imports

data = imports.get("emojis.json")


class Emoji:
    ponbus: str = data.ponbus
    yes: str = data.yes
    no: str = data.no
    nitro: str = data.nitro
    partner: str = data.partner
    dev: str = data.dev
    admin: str = data.admin
    mod: str = data.mod
    hs_balance: str = data.hs_balance
    hs_bravery: str = data.hs_bravery
    hs_brilliance: str = data.hs_brilliance
    early_supporter: str = data.early_supporter
    nitro_booster: str = data.nitro_booster
    support: str = data.support
    friend: str = data.friend
    loading: str = data.loading
    money: str = data.money
    online: str = data.online
    idle: str = data.idle
    dnd: str = data.dnd
    offline: str = data.offline
    pencil: str = "✏️"
    rainbow_emojis: list = data.rainbow_emojis
