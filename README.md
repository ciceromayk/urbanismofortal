# Catálogo de Lançamentos Imobiliários — Fortaleza/CE

Aplicação em **Streamlit** para catalogar lançamentos imobiliários em Fortaleza/CE.

## Funcionalidades

- **Mapa e catálogo** (público): localização dos empreendimentos, filtros por construtora/bairro/disponibilidade, ficha com links (tabela, plantas, imagens) e disponibilidade por tipologia.
- **Análise de mercado** (público): R$/m² por lançamento e por bairro (ponderado pela oferta), VSO acumulado, VGV em estoque estimado, mapa colorido por faixa de R$/m², gráfico área × R$/m².
- **ADM** (login): cadastrar (clique no mapa para coordenadas), editar, excluir (com confirmação pelo nome) e importar/exportar CSV.

> Indicadores são **estimativas** calculadas a partir dos dados cadastrados (preço médio ÷ área média) e exigem conferência com as tabelas oficiais das construtoras.

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # edite a senha
streamlit run app.py
```

Para testar com dados fictícios: entre como ADM → *Importar / exportar* → importe `data/exemplo_lancamentos.csv`.

## Configuração (secrets ou variáveis de ambiente)

| Chave | Obrigatória | Uso |
|---|---|---|
| `ADM_PASSWORD` | sim, para habilitar o ADM | Senha do administrador (sem ela o ADM fica desativado) |
| `ADM_USERNAME` | não (padrão `admin`) | Usuário do administrador |
| `SUPABASE_URL` / `SUPABASE_KEY` | não | Ativa persistência no Supabase |

## Persistência

- **Sem Supabase:** dados em `data/lancamentos.csv`. Em deploy na nuvem (Streamlit Cloud) o arquivo é perdido a cada reinício.
- **Com Supabase:** crie um projeto, rode `supabase_schema.sql` no SQL Editor e informe `SUPABASE_URL` e `SUPABASE_KEY` (chave `service_role`, mantida só nos secrets do servidor).

## Estrutura

- `app.py` — interface
- `storage.py` — backends CSV e Supabase
- `analytics.py` — indicadores de mercado
- `supabase_schema.sql` — tabela `lancamentos`
- `data/exemplo_lancamentos.csv` — dados fictícios

### Colunas do CSV

`id`, `nome`*, `bairro`*, `construtora`*, `endereco`, `latitude`, `longitude`, `unidades_total`, `unidades_disponiveis`, `area_media_m2`, `preco_medio`, `faixa_preco`, `previsao_entrega`, `descricao`, `link_tabela_disponibilidade`, `link_plantas`, `link_imagens`, `telefone_comercial`, `disponibilidade_tipologia` (JSON: lista de `{tipologia, metragem, disponiveis}`)

\* obrigatórias. Colunas ausentes são preenchidas vazias na importação.
