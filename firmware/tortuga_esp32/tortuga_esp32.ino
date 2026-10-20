/*
 * tortuga_esp32.ino — Nó de borda do cinto (Fase 3) · Projeto Tortuga
 * Challenge SPI 2026 · FIAP × SPI
 *
 * O servidor faz POST HTTP para  http://<ip-do-esp>/status  com:
 *   { "status":"VIOLACAO"|"CONFORME", "severity":"critica"|"alta"|"informativa",
 *     "message":"Capacete necessario", "epi":"Capacete" }
 *
 * OLED + LED verde/vermelho + buzzer + vibração. Tudo não-bloqueante (millis).
 * Compatível com o core esp32 2.x e 3.x (API do LEDC tratada com #if).
 *
 * REDE — dois modos, alternados com BOOT+RST (ver bloco abaixo):
 *   AP  (padrão) o cinto PUBLICA a rede "Tortuga-Cinto" e fica fixo em
 *                192.168.4.1. O notebook conecta nela; o cabo segue nas câmeras.
 *   STA          o cinto ENTRA numa rede existente (hotspot), via portal.
 *
 * Bibliotecas: "Adafruit SSD1306", "Adafruit GFX", "ArduinoJson" (6.x),
 *              "WiFiManager" (by tzapu — instale pelo Library Manager).
 * Placa: ESP32 Dev Module.
 *
 * Ligações (mapa real do cinto):
 *   OLED  SDA->GPIO18  SCL->GPIO22  VCC->3V3  GND->GND (endereço 0x3C)
 *   LED verde -> GPIO19 | LED vermelho -> GPIO21
 *   Buzzer -> GPIO25 (passivo) | Vibração -> GPIO26
 */

#include <WiFi.h>
#include <WebServer.h>
#include <WiFiManager.h>       // portal de configuracao de WiFi (lib "WiFiManager" by tzapu)
#include <Preferences.h>       // guarda o modo escolhido na flash (NVS)
#include "esp_wifi.h"          // economia de energia (modem-sleep)
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ════════════════════════════════════════════════════════════════════════════
//  DOIS MODOS DE REDE
//
//  MODO AP (padrao) — O CINTO E O PONTO DE ACESSO.
//    O ESP publica a rede "Tortuga-Cinto" e fica SEMPRE em 192.168.4.1.
//    O notebook conecta no Wi-Fi do cinto; o cabo de rede continua livre para
//    as cameras. Resolve tres problemas de uma vez:
//      - nao depende do Ponto de acesso movel do Windows, que se recusa a
//        ligar em rede cabeada SEM INTERNET (foi o que travou no auditorio);
//      - nao depende de internet nenhuma;
//      - acaba o IP dinamico: o endereco do cinto e sempre o mesmo, entao
//        nao ha descoberta, nao ha DHCP, nao ha IP errado registrado.
//
//  MODO STA — o cinto ENTRA numa rede existente (comportamento antigo).
//    Util quando ha hotspot disponivel, como foi na metaindustria.
//
//  COMO ALTERNAR: segure BOOT e aperte RST. O modo troca, fica salvo na flash
//  e aparece no OLED por 3 s. Nao e preciso regravar o firmware.
// ════════════════════════════════════════════════════════════════════════════
const char* AP_CINTO   = "Tortuga-Cinto";   // rede que o CINTO publica (modo AP)
const char* AP_CINTO_PW = "tortuga2026";    // senha dela (minimo 8 caracteres)
const IPAddress AP_IP(192, 168, 4, 1);      // IP FIXO do cinto no modo AP
const IPAddress AP_GW(192, 168, 4, 1);
const IPAddress AP_MASK(255, 255, 255, 0);

// Rede de configuracao do modo STA (portal do WiFiManager)
const char* AP_NAME = "Tortuga-Setup";
const char* AP_PASS = "tortuga123";

Preferences prefs;
bool gModoAP = true;            // definido no setup()

// ── Pinos (mapa REAL do cinto — confirmado pelo firmware do autor do hardware) ──
const int PIN_LED_OK   = 19;    // LED verde
const int PIN_LED_ALM  = 21;    // LED vermelho
const int PIN_BUZZER   = 25;    // buzzer passivo
const int PIN_VIBRA    = 26;    // motor de vibração
const int OLED_SDA     = 18;    // OLED I2C SDA
const int OLED_SCL     = 22;    // OLED I2C SCL
const int BUZZER_CH    = 0;     // canal LEDC (usado só no core 2.x)

// ── LEDC muda de API entre o core 2.x e 3.x — este bloco suporta os dois ──
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  #define BUZZER_BEGIN()  ledcAttach(PIN_BUZZER, 2000, 8)
  #define BUZZER_TONE(f)  ledcWriteTone(PIN_BUZZER, (f))
#else
  #define BUZZER_BEGIN()  do { ledcSetup(BUZZER_CH, 2000, 8); ledcAttachPin(PIN_BUZZER, BUZZER_CH); } while (0)
  #define BUZZER_TONE(f)  ledcWriteTone(BUZZER_CH, (f))
#endif

// ── OLED ────────────────────────────────────────────────
#define OLED_W 128
#define OLED_H 64
Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);

WebServer server(80);

// ── Estado atual do alerta ──────────────────────────────
// (prefixo SEV_ para não colidir com o símbolo 'OK' do ESP-IDF)
enum Sev { SEV_OK, SEV_INFO, SEV_ALTA, SEV_CRITICA };
volatile Sev   gSev = SEV_OK;
String         gMsg = "Tudo certo";
String         gEpi = "";
unsigned long  gLastBeep = 0, gLastBlink = 0, gLastVib = 0;
bool           gBlinkOn = false, gVibOn = false;
// ── economia de energia (Fase 4: 1–2 pilhas AA por turno de 8 h) ──
unsigned long  gStateSince = 0;            // quando o estado atual começou
bool           gOledOn = true;
const unsigned long OLED_IDLE_MS = 30000;  // apaga OLED após 30 s em CONFORME
const unsigned long ALERT_HOLD_MS = 7000;  // sem novo alerta por 7 s → volta ao verde

void oledWake() { if (!gOledOn) { oled.ssd1306_command(SSD1306_DISPLAYON); gOledOn = true; } }

// ─────────────────────────── helpers ───────────────────────────
Sev parseSev(const String& s, const String& status) {
  if (status == "CONFORME") return SEV_OK;
  if (s == "critica") return SEV_CRITICA;
  if (s == "alta")    return SEV_ALTA;
  return SEV_INFO;
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
  if (gSev == SEV_OK) {
    oled.println("CONFORME");
    oled.setTextSize(1);
    oled.setCursor(0, 44);
    oled.println("Pode trabalhar");
  } else {
    oled.println(gSev == SEV_CRITICA ? "CRITICO" : "ATENCAO");
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
  digitalWrite(PIN_LED_OK, gSev == SEV_OK ? HIGH : LOW);
  if (gSev == SEV_OK) {
    digitalWrite(PIN_LED_ALM, LOW);
    BUZZER_TONE(0);
    digitalWrite(PIN_VIBRA, LOW);
    gVibOn = false; gBlinkOn = false;
  }
  drawOled();
}

// padrões não-bloqueantes por severidade
void tick() {
  unsigned long now = millis();
  if (gSev == SEV_OK || gSev == SEV_INFO) return;   // INFO não aciona campo

  int blinkMs = (gSev == SEV_CRITICA) ? 150 : 500;   // LED vermelho
  int beepMs  = (gSev == SEV_CRITICA) ? 400 : 1200;  // buzzer
  int toneHz  = (gSev == SEV_CRITICA) ? 2300 : 1500; // freq
  int vibOn   = (gSev == SEV_CRITICA) ? 600 : 250;   // vibração ligada
  int vibOff  = (gSev == SEV_CRITICA) ? 200 : 1500;  // vibração desligada

  if (now - gLastBlink >= (unsigned)blinkMs) {
    gLastBlink = now; gBlinkOn = !gBlinkOn;
    digitalWrite(PIN_LED_ALM, gBlinkOn ? HIGH : LOW);
  }
  if (now - gLastBeep >= (unsigned)beepMs) {
    gLastBeep = now;
    BUZZER_TONE(toneHz);
    delay(80);                       // bip curto
    BUZZER_TONE(0);
  }
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
  // A assinatura "Tortuga ESP32 OK" e o que o diag_cinto.py procura na rede.
  String s = "Tortuga ESP32 OK. POST /status\n";
  s += "modo=";
  s += (gModoAP ? "AP" : "STA");
  s += "\nip=";
  s += (gModoAP ? WiFi.softAPIP().toString() : WiFi.localIP().toString());
  server.send(200, "text/plain", s);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_OK, OUTPUT);
  pinMode(PIN_LED_ALM, OUTPUT);
  pinMode(PIN_VIBRA, OUTPUT);
  BUZZER_BEGIN();

  Wire.begin(OLED_SDA, OLED_SCL);
  oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 24); oled.setTextSize(2);
  oled.println("TORTUGA"); oled.display();

  // ── Escolha do modo de rede ──────────────────────────────────────────────
  pinMode(0, INPUT_PULLUP);               // botao BOOT (GPIO0)
  prefs.begin("tortuga", false);
  gModoAP = prefs.getBool("modo_ap", true);        // padrao de fabrica: modo AP
  if (digitalRead(0) == LOW) {            // BOOT segurado no reset => ALTERNA o modo
    gModoAP = !gModoAP;
    prefs.putBool("modo_ap", gModoAP);
    Serial.printf("BOOT pressionado: modo alternado para %s\n", gModoAP ? "AP" : "STA");
    oled.clearDisplay(); oled.setTextSize(1); oled.setCursor(0, 0);
    oled.println("Modo alterado para:");
    oled.setTextSize(2); oled.setCursor(0, 18);
    oled.println(gModoAP ? "AP" : "STA");
    oled.setTextSize(1); oled.setCursor(0, 46);
    oled.println(gModoAP ? "cinto e a rede" : "cinto entra na rede");
    oled.display();
    delay(3000);
  }
  prefs.end();

  if (gModoAP) {
    // ── MODO AP: o CINTO publica a rede e fica fixo em 192.168.4.1 ──
    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(AP_IP, AP_GW, AP_MASK);      // IP fixo: nada de DHCP
    WiFi.softAP(AP_CINTO, AP_CINTO_PW);
    Serial.printf("\nMODO AP. Rede: %s  senha: %s\n", AP_CINTO, AP_CINTO_PW);
    Serial.print("IP do ESP32 (fixo): "); Serial.println(WiFi.softAPIP());

    oled.clearDisplay(); oled.setTextSize(1); oled.setCursor(0, 0);
    oled.println("CINTO = PONTO ACESSO");
    oled.drawLine(0, 10, 127, 10, SSD1306_WHITE);
    oled.setCursor(0, 16); oled.print("rede  "); oled.println(AP_CINTO);
    oled.setCursor(0, 28); oled.print("senha "); oled.println(AP_CINTO_PW);
    oled.setCursor(0, 44); oled.println("Conecte o notebook");
    oled.setCursor(0, 54); oled.print("IP "); oled.println(WiFi.softAPIP());
    oled.display();
    delay(4000);                          // tempo de ler antes de ir para CONFORME
  } else {
    // ── MODO STA: entra numa rede existente (comportamento antigo) ──
    WiFi.mode(WIFI_STA);
    WiFiManager wm;
    wm.setConfigPortalTimeout(180);       // 3 min de portal; depois reinicia e tenta de novo
    wm.setAPCallback([](WiFiManager*) {   // instrucoes no OLED quando o portal abre
      oled.clearDisplay(); oled.setTextSize(1); oled.setCursor(0, 0);
      oled.println("Config WiFi:");
      oled.print("rede "); oled.println(AP_NAME);
      oled.print("senha "); oled.println(AP_PASS);
      oled.println("abra no navegador"); oled.display();
    });
    if (!wm.autoConnect(AP_NAME, AP_PASS)) {
      Serial.println("WiFi nao configurado; reiniciando...");
      delay(1500); ESP.restart();
    }
    Serial.print("\nMODO STA. IP do ESP32: "); Serial.println(WiFi.localIP());
    oled.clearDisplay(); oled.setTextSize(1); oled.setCursor(0, 0);
    oled.println("MODO STA (na rede)");
    oled.setCursor(0, 20); oled.print("IP "); oled.println(WiFi.localIP());
    oled.display();
    delay(2500);
    esp_wifi_set_ps(WIFI_PS_MIN_MODEM);   // baixo consumo so faz sentido em STA
  }

  server.on("/", handleRoot);
  server.on("/status", handleStatus);
  server.begin();

  gSev = SEV_OK; applyState();          // inicia CONFORME (verde)
}

void loop() {
  server.handleClient();
  tick();
  // Auto-clear (push): sem novo alerta por ALERT_HOLD_MS, volta ao verde sozinho.
  if (gSev != SEV_OK && millis() - gStateSince > ALERT_HOLD_MS) {
    gSev = SEV_OK; applyState();
  }
  // Economia: após 30 s em CONFORME, apaga o OLED (o LED verde segue indicando).
  if (gSev == SEV_OK && gOledOn && millis() - gStateSince > OLED_IDLE_MS) {
    oled.ssd1306_command(SSD1306_DISPLAYOFF); gOledOn = false;
  }
}
