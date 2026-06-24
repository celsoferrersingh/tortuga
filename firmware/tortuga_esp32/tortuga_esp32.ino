/*
 * tortuga_esp32.ino — Nó de borda do cinto (Fase 3) · Projeto Tortuga
 * Challenge SPI 2026 · FIAP × SPI
 *
 * O backend (notifier.py) faz POST HTTP para  http://<ip-do-esp>/status  com:
 *   { "status":"VIOLACAO"|"CONFORME", "severity":"critica"|"alta"|"informativa",
 *     "message":"Capacete necessário", "epi":"Capacete" }
 *
 * O ESP responde no posto de trabalho, fechando o ciclo "da detecção à ação":
 *   • OLED 0,96" SSD1306  → CONFORME / mensagem da violação
 *   • LED verde / vermelho → conformidade legível à distância
 *   • Buzzer               → alerta sonoro (padrão por severidade)
 *   • Motor de vibração    → feedback tátil no cinto (o operador se corrige)
 *
 * Tudo NÃO-BLOQUEANTE (millis): o alerta pulsa enquanto o estado estiver ativo
 * e volta ao verde quando chega um CONFORME.
 *
 * Bibliotecas (Library Manager): "Adafruit SSD1306", "Adafruit GFX",
 * "ArduinoJson". Placa: ESP32 Dev Module.
 *
 * Ligações (ESP32 DevKit v1):
 *   OLED  SDA->GPIO21  SCL->GPIO22  VCC->3V3  GND->GND
 *   LED verde   -> GPIO25  (+ resistor 220Ω)
 *   LED vermelho-> GPIO26  (+ resistor 220Ω)
 *   Buzzer      -> GPIO27  (passivo, via canal LEDC)
 *   Vibração    -> GPIO14  (motor via transistor NPN/MOSFET + diodo flyback)
 */

#include <WiFi.h>
#include <WebServer.h>
#include "esp_wifi.h"          // controle de economia de energia (modem-sleep)
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ── Wi-Fi ───────────────────────────────────────────────
const char* WIFI_SSID = "SUA_REDE";
const char* WIFI_PASS = "SUA_SENHA";

// ── Pinos ───────────────────────────────────────────────
const int PIN_LED_OK   = 25;
const int PIN_LED_ALM  = 26;
const int PIN_BUZZER   = 27;
const int PIN_VIBRA    = 14;
const int BUZZER_CH    = 0;     // canal LEDC do ESP32

// ── OLED ────────────────────────────────────────────────
#define OLED_W 128
#define OLED_H 64
Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);

WebServer server(80);

// ── Estado atual do alerta ──────────────────────────────
enum Sev { OK, INFO, ALTA, CRITICA };
volatile Sev   gSev = OK;
String         gMsg = "Tudo certo";
String         gEpi = "";
unsigned long  gLastBeep = 0, gLastBlink = 0, gLastVib = 0;
bool           gBlinkOn = false, gVibOn = false;
// ── economia de energia (Fase 4: 1–2 pilhas AA por turno de 8 h) ──
unsigned long  gStateSince = 0;            // quando o estado atual começou
bool           gOledOn = true;
const unsigned long OLED_IDLE_MS = 30000;  // apaga OLED após 30 s em CONFORME

void oledWake() { if (!gOledOn) { oled.ssd1306_command(SSD1306_DISPLAYON); gOledOn = true; } }

// ─────────────────────────── helpers ───────────────────────────
Sev parseSev(const String& s, const String& status) {
  if (status == "CONFORME") return OK;
  if (s == "critica") return CRITICA;
  if (s == "alta")    return ALTA;
  return INFO;
}

void drawOled() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.println("TORTUGA  CONTROLE EPI");
  oled.drawLine(0, 10, 127, 10, SSD1306_WHITE);
  oled.setTextSize(2);
  oled.setCursor(0, 18);
  if (gSev == OK) {
    oled.println("CONFORME");
    oled.setTextSize(1);
    oled.setCursor(0, 44);
    oled.println("Pode trabalhar");
  } else {
    oled.println(gSev == CRITICA ? "CRITICO" : "ATENCAO");
    oled.setTextSize(1);
    oled.setCursor(0, 40);
    oled.println(gMsg.substring(0, 21));
    if (gEpi.length()) { oled.setCursor(0, 52); oled.print("EPI: "); oled.println(gEpi); }
  }
  oled.display();
}

void applyState() {
  gStateSince = millis();
  oledWake();                 // qualquer novo veredito acende o OLED
  // LEDs
  digitalWrite(PIN_LED_OK, gSev == OK ? HIGH : LOW);
  if (gSev == OK) {
    digitalWrite(PIN_LED_ALM, LOW);
    ledcWriteTone(BUZZER_CH, 0);
    digitalWrite(PIN_VIBRA, LOW);
    gVibOn = false; gBlinkOn = false;
  }
  drawOled();
}

// padrões não-bloqueantes por severidade
void tick() {
  unsigned long now = millis();
  if (gSev == OK || gSev == INFO) return;   // INFO não aciona campo (só dashboard)

  // intervalos por severidade
  int blinkMs = (gSev == CRITICA) ? 150 : 500;   // LED vermelho
  int beepMs  = (gSev == CRITICA) ? 400 : 1200;  // buzzer
  int tone    = (gSev == CRITICA) ? 2300 : 1500; // freq
  int vibOn   = (gSev == CRITICA) ? 600 : 250;   // vibração ligada
  int vibOff  = (gSev == CRITICA) ? 200 : 1500;  // vibração desligada

  // LED vermelho piscando
  if (now - gLastBlink >= (unsigned)blinkMs) {
    gLastBlink = now; gBlinkOn = !gBlinkOn;
    digitalWrite(PIN_LED_ALM, gBlinkOn ? HIGH : LOW);
  }
  // buzzer em pulsos
  if (now - gLastBeep >= (unsigned)beepMs) {
    gLastBeep = now;
    ledcWriteTone(BUZZER_CH, tone);
    delay(80);                       // bip curto
    ledcWriteTone(BUZZER_CH, 0);
  }
  // vibração pulsante
  int vibPeriod = gVibOn ? vibOn : vibOff;
  if (now - gLastVib >= (unsigned)vibPeriod) {
    gLastVib = now; gVibOn = !gVibOn;
    digitalWrite(PIN_VIBRA, gVibOn ? HIGH : LOW);
  }
}

// ─────────────────────────── HTTP ───────────────────────────
void handleStatus() {
  if (server.method() != HTTP_POST) { server.send(405, "text/plain", "POST"); return; }
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, server.arg("plain"));
  if (err) { server.send(400, "application/json", "{\"ok\":false}"); return; }

  String status = doc["status"] | "VIOLACAO";
  String sev    = doc["severity"] | "alta";
  gMsg = String((const char*)(doc["message"] | "Atencao a seguranca"));
  gEpi = String((const char*)(doc["epi"] | ""));
  gSev = parseSev(sev, status);
  applyState();
  server.send(200, "application/json", "{\"ok\":true}");
}

void handleRoot() {
  server.send(200, "text/plain", "Tortuga ESP32 OK. POST /status");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_OK, OUTPUT);
  pinMode(PIN_LED_ALM, OUTPUT);
  pinMode(PIN_VIBRA, OUTPUT);
  ledcSetup(BUZZER_CH, 2000, 8);
  ledcAttachPin(PIN_BUZZER, BUZZER_CH);

  Wire.begin(21, 22);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 24); oled.setTextSize(2);
  oled.println("TORTUGA"); oled.display();

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.print("\nIP do ESP32: "); Serial.println(WiFi.localIP());

  // Modem-sleep: o radio Wi-Fi dorme entre beacons (DTIM) e acorda para receber.
  // Derruba o consumo medio de ~120 mA para ~20-40 mA SEM perder o push do
  // servidor — mantem a latencia <1 s do alerta critico. Chave para as 8 h.
  esp_wifi_set_ps(WIFI_PS_MIN_MODEM);

  server.on("/", handleRoot);
  server.on("/status", handleStatus);
  server.begin();

  gSev = OK; applyState();          // inicia CONFORME (verde)
}

void loop() {
  server.handleClient();
  tick();
  // Economia: após 30 s em CONFORME, apaga o OLED (o LED verde segue indicando).
  // Qualquer alerta novo reacende a tela via applyState()/oledWake().
  if (gSev == OK && gOledOn && millis() - gStateSince > OLED_IDLE_MS) {
    oled.ssd1306_command(SSD1306_DISPLAYOFF); gOledOn = false;
  }
}
