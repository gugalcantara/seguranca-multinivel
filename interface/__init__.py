"""Interface Tkinter: tela inicial, autenticação, consulta ao acervo, cadastro,
termo de consentimento e painel de gerenciamento.

Nenhum SQL e nenhuma decisão de acesso moram aqui: as telas chamam o motor
(autenticacao/), o serviço de acervo (acervo/entrega.py) e os repositórios
(dados/). A camada visual compartilhada — paleta, estilos ttk, `Cartao`,
`Tabela` e o dimensionamento das janelas — está em tema.py.
"""
