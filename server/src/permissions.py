from .config import cfg
from .db.models.user import User


def is_admin(user: User) -> bool:
    return user.name == cfg().general.admin_user


def can_create_campaigns(user: User) -> bool:
    return user.can_create_campaigns or is_admin(user)


def get_asset_quota(user: User) -> int:
    if user.asset_quota is not None:
        return user.asset_quota
    return cfg().assets.max_total_asset_size_in_bytes
