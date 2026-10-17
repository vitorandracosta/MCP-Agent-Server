# RAG — Geração Aumentada por Recuperação

Retrieval-Augmented Generation (RAG) é a técnica de buscar trechos
relevantes numa base de documentos e incluí-los no prompt antes de o
modelo de linguagem responder. Assim o modelo responde com base em
informação que não estava no seu treinamento, e é possível citar a fonte.

## Etapas de indexação

1. **Extração**: o texto é retirado de cada arquivo (TXT, Markdown, PDF, DOCX).
2. **Chunking**: o texto é dividido em pedaços (por exemplo, 800
   caracteres com 120 de sobreposição, para não cortar ideias ao meio).
3. **Embeddings**: cada pedaço vira um vetor numérico por meio de um
   modelo como o all-MiniLM-L6-v2, que gera vetores de 384 dimensões.
4. **Armazenamento**: os vetores vão para um banco vetorial (ChromaDB).

## Etapas de consulta

1. A pergunta do usuário também vira um vetor.
2. O banco retorna os k pedaços mais próximos, normalmente pela
   similaridade de cosseno (1 = mesmo sentido, 0 = sem relação).
3. Os pedaços entram no contexto do modelo, junto com a pergunta.

## Cuidados

- Modelos de embedding treinados só em inglês recuperam pior textos em
  português; modelos multilíngues resolvem isso.
- PDFs escaneados (imagem) não têm texto extraível sem OCR.
- Reindexação incremental evita reprocessar arquivos que não mudaram.
