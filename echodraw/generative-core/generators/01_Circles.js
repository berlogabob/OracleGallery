// Boilerplate for Pattern Generator in p5.js (echodraw-project)
// Настройки для поля и сетки
let fieldWidth = 180; // Ширина поля в мм (для плотера)
let fieldHeight = 180; // Высота поля в мм
let numCellsX = 50; // Количество ячеек по ширине
let numCellsY = 50; // Количество ячеек по высоте
let DPI = 96; // DPI для масштаба (экран/плотер; для NEJE ~254 DPI?)

// Настройки паттерна (круги)
let useFaces = true; // true: центры ячеек (faces), false: перекрестья (vertices)
let circleDiameter = 0.5; // Диаметр в % от размера ячейки (0-1)
let padding = 0; // Отступ от краёв ячейки в мм

// Внутренние переменные
let canvasWidth, canvasHeight; // Размер canvas в пикселях
let cellWidth, cellHeight; // Размер ячейки в мм
let paths = []; // Массив путей для G-code экспорта

function setup() {
  // Масштабируем canvas под DPI
  canvasWidth = (fieldWidth / 25.4) * DPI; // мм в дюймы * DPI
  canvasHeight = (fieldHeight / 25.4) * DPI;
  createCanvas(canvasWidth, canvasHeight);
  noLoop(); // Рисуем один раз (или loop для реал-тайм)

  // Рассчитываем размеры ячеек
  cellWidth = fieldWidth / numCellsX;
  cellHeight = fieldHeight / numCellsY;

  generatePattern(); // Генерируем паттерн
}

function draw() {
  background(255);
  stroke(0);
  noFill();

  // Опционально: рисуем сетку для отладки
  drawGrid();

  // Рисуем паттерн (круги)
  for (let path of paths) {
    beginShape();
    for (let pt of path) {
      // Масштабируем точки под canvas (мм -> пиксели)
      let x = (pt.x / fieldWidth) * canvasWidth;
      let y = (pt.y / fieldHeight) * canvasHeight;
      vertex(x, y);
    }
    endShape(CLOSE);
  }
}

// Функция генерации паттерна (круги в ячейках)
function generatePattern() {
  paths = []; // Очищаем пути

  let effectiveDiameter =
    Math.min(cellWidth, cellHeight) * circleDiameter - padding * 2;

  if (useFaces) {
    // Режим faces: центры ячеек
    for (let i = 0; i < numCellsX; i++) {
      for (let j = 0; j < numCellsY; j++) {
        let centerX = (i + 0.5) * cellWidth;
        let centerY = (j + 0.5) * cellHeight;
        paths.push(generateCirclePath(centerX, centerY, effectiveDiameter / 2));
      }
    }
  } else {
    // Режим vertices: перекрестья (углы ячеек)
    for (let i = 0; i <= numCellsX; i++) {
      for (let j = 0; j <= numCellsY; j++) {
        let posX = i * cellWidth;
        let posY = j * cellHeight;
        paths.push(generateCirclePath(posX, posY, effectiveDiameter / 2));
      }
    }
  }
}

// Генератор пути для круга (аппроксимация линиями для G-code; 32 сегмента для гладкости)
function generateCirclePath(cx, cy, r) {
  let segments = 32;
  let path = [];
  for (let a = 0; a < TWO_PI; a += TWO_PI / segments) {
    let x = cx + cos(a) * r;
    let y = cy + sin(a) * r;
    path.push({ x: x, y: y });
  }
  return path;
}

// Опциональная сетка для визуализации
function drawGrid() {
  stroke(200); // Светлый цвет
  for (let i = 0; i <= numCellsX; i++) {
    let x = (i / numCellsX) * canvasWidth;
    line(x, 0, x, canvasHeight);
  }
  for (let j = 0; j <= numCellsY; j++) {
    let y = (j / numCellsY) * canvasHeight;
    line(0, y, canvasWidth, y);
  }
  stroke(0); // Восстанавливаем
}

// Экспорт в G-code (простой: G1 для линий, Z для подъёма)
function exportGCode() {
  let gcode = [];
  gcode.push("G21; мм");
  gcode.push("G90; Абсолютные координаты");
  gcode.push("G0 Z5; Подъём"); // Безопасная высота

  for (let path of paths) {
    if (path.length > 0) {
      // Перейти к старту
      gcode.push(`G0 X${path[0].x.toFixed(2)} Y${path[0].y.toFixed(2)}`);
      gcode.push("G0 Z0; Опустить");

      for (let pt of path) {
        gcode.push(`G1 X${pt.x.toFixed(2)} Y${pt.y.toFixed(2)}`);
      }
      // Закрыть путь (вернуться к старту)
      gcode.push(`G1 X${path[0].x.toFixed(2)} Y${path[0].y.toFixed(2)}`);
      gcode.push("G0 Z5; Подъём");
    }
  }

  gcode.push("G0 X0 Y0; Домой");
  console.log(gcode.join("\n")); // Вывод в консоль; можно сохранить в файл
}

// Для теста: вызови exportGCode() в console после запуска
