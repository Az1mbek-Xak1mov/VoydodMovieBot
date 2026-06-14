from aiogram.fsm.state import State, StatesGroup


class AddChannelFSM(StatesGroup):
    waiting_for_channel = State()


class AddMovieFSM(StatesGroup):
    waiting_for_video = State()
    waiting_for_code = State()
    waiting_for_metadata = State()


class ImageFSM(StatesGroup):
    # Text-to-image: waiting for the prompt.
    waiting_for_gen_prompt = State()
    # Image edit: collecting reference image(s) and then the edit prompt
    # in the same state (a photo extends the set, text triggers the edit).
    waiting_for_edit_input = State()
