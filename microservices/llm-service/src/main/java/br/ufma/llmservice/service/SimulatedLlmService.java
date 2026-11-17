package br.ufma.llmservice.service;

import org.springframework.stereotype.Service;

@Service
public class SimulatedLlmService {

    public String generate(String prompt, long delayMs) {

        if (delayMs < 0 || delayMs > 10000) {
            throw new IllegalArgumentException(
                    "O tempo deve estar entre 0 e 10000 ms"
            );
        }

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Processamento interrompido", e
            );
        }

        return "Resposta simulada para: " + prompt;
    }
}
