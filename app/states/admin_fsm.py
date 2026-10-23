from aiogram.fsm.state import State, StatesGroup


class AddChannelFSM(StatesGroup):
    waiting_for_channel = State()


class AddMovieFSM(StatesGroup):
    waiting_for_video = State()
    waiting_for_code = State()
    waiting_for_metadata = State()
