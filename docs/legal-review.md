# Revisao Juridica e Avaliacao de Qualidade

Nenhum caso desta base foi aprovado por profissional neste trabalho de desenvolvimento.
Os artigos e estados esperados sao hipoteses de teste, nao pareceres.

## Processo de Revisao

1. Um profissional qualificado deve ler a pergunta e os fatos do caso, consultar a norma e sua vigencia e verificar os trechos do PDF. A edicao fornecida e PROCON-SP 2025; confirme atualizacoes antes de publicar orientacoes.
2. Corrigir `expected_status`, `candidate_articles` e consultas auxiliares em `data/evaluation/cases.json`. Nao ajustar as expectativas apenas para fazer o programa passar.
3. Executar `python -m backend.evaluate --mode live` somente com autorizacao para consumo de API. Conferir as duas versoes de cada resposta no relatorio.
4. Verificar: conclusao sustentada, fatos nao inventados, condicoes e excecoes, artigos/paginas corretos, citacao fiel, ausencia de promessa de resultado, linguagem simples sem perder ressalvas e concordancia entre as duas versoes.
5. Registrar no campo `review`: `status` (`approved` ou `rejected`), `reviewer`, `credential` (por exemplo, identificacao profissional pertinente), `reviewed_at` (AAAA-MM-DD) e `notes` com justificativa e fontes verificadas. O registro e manual e nao autentica credenciais.
6. Versionar a revisao com revisao de codigo e repetir quando mudar modelo, prompt, parser, fonte normativa ou politica de recuperacao. A aprovacao de uma expectativa nao aprova automaticamente novas respostas.

## Tipos de Evidencia

- `--mode lexical`: teste offline da recuperacao. Compara pergunta original e expansao com consultas predefinidas. Nao mede a reformulacao real pelo modelo nem a qualidade juridica da resposta.
- `--mode live`: executa geracao real e registra respostas dos casos de teste. Tem custo e continua exigindo leitura humana.
- `--approved-only`: avalia somente referencias aprovadas; falha se nenhuma existir.
- `--require-reviewed`: bloqueia a avaliacao quando houver caso sem aprovacao registrada.

Sinais de tamanho das frases e palavras dificeis nao equivalem a prova de legibilidade.
Acertar um numero de artigo tambem nao comprova a aplicacao correta da lei.
Nao use relatos reais com dados pessoais nesta base versionada; anonimize ou crie casos sinteticos.