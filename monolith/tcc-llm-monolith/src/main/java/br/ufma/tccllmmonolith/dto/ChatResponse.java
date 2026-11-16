package br.ufma.tccllmmonolith.dto;

public record ChatResponse(
        String response,
        long processingTimeMs
) {}
