package br.ufma.chatservice.dto;

public record ChatRequest(
        String prompt,
        long delayMs
) {
}
