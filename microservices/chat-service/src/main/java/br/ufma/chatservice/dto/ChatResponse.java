package br.ufma.chatservice.dto;

public record ChatResponse(
        String response,
        long processingTimeMs
) {
}
