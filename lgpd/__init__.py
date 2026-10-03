"""Conformidade com a LGPD (Lei 13.709/2018) no tratamento da imagem facial.

Imagem de rosto é dado pessoal SENSÍVEL (art. 5º, II), e tratá-la exige
consentimento específico e destacado (art. 11, I), colhido ANTES do tratamento
(art. 9º). Aqui mora o texto do termo e o cálculo do hash que prova qual versão
foi apresentada — provar o consentimento é ônus do controlador (art. 8º, §2º).

A tela que apresenta o termo fica em interface/termo.py; o registro do aceite,
em dados.repositorio.RepositorioConsentimento.
"""
