"""CivitAI Browser settings registration for SD WebUI."""

import gradio as gr
from modules import shared, script_callbacks


def on_ui_settings():
    section = ("civitai_browser_new", "CivitAI Browser")

    shared.opts.add_option(
        "civitai_api_key",
        shared.OptionInfo(
            "", "Personal CivitAI API key", section=section
        ).info("Required for some downloads. Get yours at civitai.com/user/account")
    )

    shared.opts.add_option(
        "civitai_auto_organize",
        shared.OptionInfo(
            True, "Auto-organize downloads by BaseModel / Author / ModelName",
            section=section
        )
    )

    shared.opts.add_option(
        "civitai_max_concurrent",
        shared.OptionInfo(
            2, "Maximum concurrent downloads",
            gr.Slider, {"minimum": 1, "maximum": 5, "step": 1},
            section=section
        )
    )

    shared.opts.add_option(
        "civitai_use_aria2",
        shared.OptionInfo(
            True, "Use Aria2 for downloads (faster, resumable)",
            section=section
        ).info("Falls back to standard HTTP if Aria2 is not available")
    )

    shared.opts.add_option(
        "civitai_default_nsfw",
        shared.OptionInfo(
            False, "Show NSFW content by default",
            section=section
        )
    )

    shared.opts.add_option(
        "civitai_proxy",
        shared.OptionInfo(
            "", "HTTP proxy (e.g. http://127.0.0.1:7890)",
            section=section
        )
    )


script_callbacks.on_ui_settings(on_ui_settings)
