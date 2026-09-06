/*
 * tortuga_discover.ino — Descoberta de pinos do cinto · Projeto Tortuga
 *
 * Roda UMA vez pra mapear o hardware do cinto (que foi montado à mão):
 *   1) Varre o barramento I2C em vários pares de pinos → acha o OLED (endereço + SDA/SCL).
 *   2) Acende um GPIO de cada vez (1,5 s) anunciando no Serial → você vê qual é
 *      o LED verde, o LED vermelho, o buzzer e o motor de vibração.
 *
 * Use: grave este sketch, abra o Serial Monitor a 115200, e ANOTE:
 *   - o endereço I2C e o par SDA/SCL do OLED (aparece uma vez, no começo);
 *   - qual GPIO acende o VERDE, qual acende o VERMELHO, qual APITA, qual VIBRA.
 * Depois me manda essas 6 informações que eu configuro o firmware final.
 */
#include <Wire.h>

// pares (SDA, SCL) mais comuns pra tentar achar o OLED
int I2C_PAIRS[][2] = {
  {21,22},{22,21},{4,5},{5,4},{16,17},{17,16},{32,33},{33,32},
  {25,26},{26,25},{13,15},{15,13},{18,19},{19,18},{23,19},{14,27}
};
// GPIOs de saída candidatos (sem os só-de-entrada 34/35/36/39)
int OUT_PINS[] = {2,4,5,12,13,14,15,16,17,18,19,21,22,23,25,26,27,32,33};

void scanPair(int sda, int scl) {
  Wire.begin(sda, scl);
  delay(60);
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.print(">>> OLED/I2C ENCONTRADO! endereco 0x");
      Serial.print(a, HEX);
      Serial.print("  |  SDA=GPIO"); Serial.print(sda);
      Serial.print("  SCL=GPIO"); Serial.println(scl);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n=== TORTUGA · descoberta de pinos ===");
  Serial.println("[1] Procurando o OLED no I2C (varias combinacoes)...");
  for (auto& p : I2C_PAIRS) scanPair(p[0], p[1]);
  Serial.println("    (se nao apareceu nenhum '>>> OLED/I2C ENCONTRADO', me avise)");
  Serial.println("\n[2] Vou acender um GPIO de cada vez. OLHE A PLACA e anote:");
  Serial.println("    qual acende o LED VERDE, o VERMELHO, qual APITA, qual VIBRA.\n");
  for (int p : OUT_PINS) pinMode(p, OUTPUT), digitalWrite(p, LOW);
}

void loop() {
  for (int p : OUT_PINS) {
    Serial.println("");
    Serial.print(">>>>>> PROXIMO PINO: GPIO "); Serial.print(p);
    Serial.println("  (ativa em 1,5 s — preste atencao no BIP e na VIBRACAO)");
    delay(1500);
    Serial.print("       ATIVANDO GPIO "); Serial.print(p); Serial.println(" AGORA <<<<<<");
    digitalWrite(p, HIGH);
    delay(2500);                 // fica ligado 2,5 s
    digitalWrite(p, LOW);
    delay(2500);                 // silencio 2,5 s antes do proximo
  }
  Serial.println("\n--- fim da volta, repetindo. Feche o Serial quando ja anotou. ---\n");
  delay(1500);
}
