import logging
import sys

import pygame

from src.config_loader import ConfigLoader
from src.audio import AudioEngine
from src.color import ColorMapper
from src.animation import AnimationEngine
from src.visualizer import Visualizer


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config_loader = ConfigLoader("config.yaml")
    config = config_loader.get()

    audio_engine = AudioEngine(config)
    color_mapper = ColorMapper(config)
    animation_engine = AnimationEngine(config)
    visualizer = Visualizer(config, audio_engine, color_mapper, animation_engine, config_loader)

    visualizer.run()


if __name__ == "__main__":
    main()
