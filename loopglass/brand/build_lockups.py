"""Rebuild the outlined Loopglass wordmarks; no font is needed to display the result."""

import sys
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgGenerator

OUT = Path(__file__).resolve().parent
CYAN = QColor("#6bdcf1")
GREEN = QColor("#78f5a5")
INK = QColor("#0c1316")
PAPER = QColor("#e4f5ef")


def draw_mark(painter: QPainter):
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(INK)
    painter.drawRoundedRect(QRectF(4, 4, 120, 120), 30, 30)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor("#315057"), 1.5))
    painter.drawRoundedRect(QRectF(4.75, 4.75, 118.5, 118.5), 29.25, 29.25)
    loop = QPainterPath()
    loop.arcMoveTo(QRectF(26.5, 26.5, 75, 75), 60)
    loop.arcTo(QRectF(26.5, 26.5, 75, 75), 60, 240)
    pen = QPen(CYAN, 9.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawPath(loop)
    letter = QPainterPath()
    letter.moveTo(51, 47.5)
    letter.lineTo(51, 78.5)
    letter.lineTo(74.5, 78.5)
    pen.setColor(PAPER)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(letter)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(GREEN)
    painter.drawEllipse(QRectF(84, 56.5, 15, 15))


def build(filename: str, word_color: QColor):
    generator = QSvgGenerator()
    generator.setFileName(str(OUT / filename))
    generator.setSize(QSize(602, 128))
    generator.setViewBox(QRect(0, 0, 602, 128))
    generator.setTitle("Loopglass wordmark")
    generator.setDescription("Outlined Loopglass wordmark and loopback lens mark")
    painter = QPainter(generator)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_mark(painter)
    font = QFont("Noto Sans")
    font.setPixelSize(63)
    font.setWeight(QFont.Weight.DemiBold)
    word = QPainterPath()
    word.addText(150, 85, font, "Loopglass")
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(word_color)
    painter.drawPath(word)
    painter.end()


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    build("loopglass-lockup-dark.svg", PAPER)
    build("loopglass-lockup-light.svg", INK)
