from peewee import JOIN
from playhouse.shortcuts import update_model_from_dict

import auth
from .initiative import send_client_initiatives
from app import app, logger, sio, state
from models import (
    Initiative,
    InitiativeLocationData,
    Layer,
    Location,
    LocationUserOption,
    Note,
    Shape,
)


@auth.login_required(app, sio)
async def load_location(sid, location):
    sid_data = state.sid_map[sid]
    user = sid_data["user"]
    room = sid_data["room"]

    sid_data["location"] = location

    data = {}
    data["locations"] = [l.name for l in room.locations]
    if user == room.creator:
        data["layers"] = [
            l.as_dict(user, True) for l in location.layers.order_by(Layer.index)
        ]
    else:
        data["layers"] = [
            l.as_dict(user, False)
            for l in location.layers.order_by(Layer.index).where(Layer.player_visible)
        ]
    client_options = user.as_dict()
    client_options.update(
        **LocationUserOption.get(user=user, location=location).as_dict()
    )

    await sio.emit("Board.Set", data, room=sid, namespace="/planarally")
    await sio.emit(
        "Location.Set", location.as_dict(), room=sid, namespace="/planarally"
    )
    await sio.emit(
        "Client.Options.Set", client_options, room=sid, namespace="/planarally"
    )
    await sio.emit(
        "Notes.Set",
        [
            note.as_dict()
            for note in Note.select().where((Note.user == user) & (Note.room == room))
        ],
        room=sid,
        namespace="/planarally",
    )

    sorted_initiatives = [
        init.as_dict()
        for init in Initiative.select()
        .join(Shape, JOIN.LEFT_OUTER, on=(Initiative.uuid == Shape.uuid))
        .join(Layer)
        .where((Layer.location == location))
        .order_by(Initiative.index)
    ]
    location_data = InitiativeLocationData.get_or_none(location=location)
    if location_data:
        await send_client_initiatives(room, location, user)
        await sio.emit(
            "Initiative.Round.Update",
            location_data.round,
            room=sid,
            namespace="/planarally",
        )
        await sio.emit(
            "Initiative.Turn.Set", location_data.turn, room=sid, namespace="/planarally"
        )


@sio.on("Location.Delete", namespace="/planarally")
@auth.login_required(app, sio)
async def delete_location(sid, location):
    sid_data = state.sid_map[sid]
    user = sid_data["user"]
    room = sid_data["room"]
    active_location = room.get_active_location(dm=True)

    if room.creator != user:
        logger.warning(f"{user.name} attempted to delete location")
        return

    if location == active_location.name:
        logger.warning(f"{user.name} attempted suicide")
        return

    location_object = Location.get(room=room, name=location)
    location_object.delete_instance()
    location_object.save()
    await load_location(sid, active_location)


@sio.on("Location.Change", namespace="/planarally")
@auth.login_required(app, sio)
async def change_location(sid, location):
    sid_data = state.sid_map[sid]
    user = sid_data["user"]
    room = sid_data["room"]

    if room.creator != user:
        logger.warning(f"{user.name} attempted to change location")
        return

    old_location = room.get_active_location(dm=True)
    sio.leave_room(sid, old_location.get_path(), namespace="/planarally")
    room.dm_location = location
    new_location = room.get_active_location(dm=True)

    sio.enter_room(sid, new_location.get_path(), namespace="/planarally")
    await load_location(sid, new_location)

    room.player_location = location
    room.save()

    for room_player in room.players:
        for psid in state.get_sids(user=room_player.player, room=room):
            sio.leave_room(psid, old_location.get_path(), namespace="/planarally")
            sio.enter_room(psid, new_location.get_path(), namespace="/planarally")
            await load_location(psid, new_location)


@sio.on("Location.Options.Set", namespace="/planarally")
@auth.login_required(app, sio)
async def set_location_options(sid, data):
    sid_data = state.sid_map[sid]
    user = sid_data["user"]
    room = sid_data["room"]
    location = sid_data["location"]

    if room.creator != user:
        logger.warning(f"{user.name} attempted to set a room option")
        return

    update_model_from_dict(location, data)
    location.save()

    await sio.emit(
        "Location.Set",
        data,
        room=location.get_path(),
        skip_sid=sid,
        namespace="/planarally",
    )


@sio.on("Location.New", namespace="/planarally")
@auth.login_required(app, sio)
async def add_new_location(sid, location):
    sid_data = state.sid_map[sid]
    user = sid_data["user"]
    room = sid_data["room"]

    if room.creator != user:
        logger.warning(f"{user.name} attempted to add a new location")
        return

    new_location = Location.create(room=room, name=location)
    new_location.add_default_layers()

    await load_location(sid, new_location)
