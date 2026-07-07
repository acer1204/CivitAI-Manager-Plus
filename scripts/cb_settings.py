"""CivitAI Manager Plus settings registration for SD WebUI."""

import gradio as gr
from modules import shared, script_callbacks


def on_ui_settings():
    section = ("civitai_browser_new", "CivitAI Manager Plus")

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

    # v1.3 — separate card-size sliders for Browse (search results) and
    # Installed grids. Values are in em (browser font-size units) so they
    # scale with the WebUI zoom. Preview media height auto-tracks width at
    # a fixed 1.4 ratio (portrait, matches CivitAI's typical preview shape).
    shared.opts.add_option(
        "civitai_browse_card_width",
        shared.OptionInfo(
            10, "Browse — card width (em)",
            gr.Slider, {"minimum": 6, "maximum": 20, "step": 1},
            section=section
        ).info("Card width for the Browse (search results) grid. "
               "Larger = fewer per row but bigger previews. Refresh the "
               "browser tab after changing.")
    )

    shared.opts.add_option(
        "civitai_installed_card_width",
        shared.OptionInfo(
            10, "Installed — card width (em)",
            gr.Slider, {"minimum": 6, "maximum": 20, "step": 1},
            section=section
        ).info("Card width for the Installed grid. Refresh the browser "
               "tab after changing.")
    )

    # Page size for the Installed grid. Rendering the full library at once
    # jams the browser on large collections, so we paginate — this option
    # lets the user pick the batch size (100 is the shipped default).
    # "All" disables pagination.
    shared.opts.add_option(
        "civitai_installed_page_size",
        shared.OptionInfo(
            "100", "Installed — cards per page",
            gr.Radio, {"choices": ["50", "100", "200", "All"]},
            section=section
        ).info("How many installed cards render at once. Larger = fewer "
               "page flips but slower filter response on big libraries. "
               "Refresh the browser tab after changing.")
    )


script_callbacks.on_ui_settings(on_ui_settings)
