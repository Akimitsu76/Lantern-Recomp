# Componentes públicos

O launcher Aster Native não inclui conteúdo do jogo. O código específico do
dump é produzido somente no computador do usuário e não faz parte do pacote.

Os pacotes portáteis incluem Python (licença PSF), Tcl/Tk (licença Tcl/Tk),
PyInstaller (GPL com exceção para o bootloader), CMake (BSD) e Ninja (Apache 2.0).
As licenças fornecidas pelos componentes são copiadas para `LICENSES` no pacote.
O Python Linux é proveniente de `astral-sh/python-build-standalone`; o Python
Windows é o instalador oficial de python.org, preparado em prefixo Wine isolado.

O AppImage também inclui o runtime oficial `AppImage/type2-runtime`.
Seu aviso de licença acompanha os recursos em `LICENSES/AppImage-runtime-LICENSE`.
O appimagetool é usado apenas para empacotar, sem ser incorporado ao launcher.

ReXGlue SDK 0.10.0 é baixado separadamente do release oficial
https://github.com/rexglue/rexglue-sdk/releases/tag/v0.10.0, com hashes fixados.
O SDK e os derivados Xenia usam a licença BSD indicada em seu arquivo LICENSE.
O patch público de cache mantém os avisos originais nas fontes baixadas.
glslang também é baixado em commit fixado para fornecer headers compatíveis.
As licenças desses componentes permanecem nas respectivas árvores do SDK.

Os nomes Green Lantern e Rise of the Manhunters identificam o jogo compatível;
este launcher experimental não é uma distribuição do jogo nem uma versão
oficial. É necessário fornecer os próprios arquivos do dump suportado.

## AMD FidelityFX Super Resolution 1

A reconstrução EASU usa `ffx_a.h` e `ffx_fsr1.h` originais da AMD, sob licença MIT, revisão `a21ffb8f6c13233ba336352bdff293894c706575` de https://github.com/GPUOpen-Effects/FidelityFX-FSR. A licença integral acompanha `integrations/rexglue/presenter-filter/FSR-LICENSE.txt`; origem e hashes constam em `FSR-SOURCE.json`. Os shaders SPIR-V EASU compilados derivam desses headers e do adaptador original do projeto. Não são shaders extraídos do jogo.

## NVIDIA FXAA Quality 3.11 (Vulkan adapter)

The Vulkan adapter uses the unmodified `Fxaa3_11.h` from Intel GameTechDev's
CMAA2 sample at commit `d0ec9097335f740c6dd7ea1ff3f4336fc6e11a40`, originally
NVIDIA FXAA 3.11 by Timothy Lottes. Source, SHA256 and adapter parameters are
recorded in `integrations/rexglue/swap-aa/FXAA-SOURCE.json`. The existing D3D12
FXAA Quality bytecode is retained. The following license also applies to the
source embedded in public SDK patch 0031:

// File:        FXAA\src/FXAA3_11.h
// SDK Version: v1.2 
// Email:       gameworks@nvidia.com
// Site:        http://developer.nvidia.com/
//
// Copyright (c) 2014, NVIDIA CORPORATION. All rights reserved.
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions
// are met:
//  * Redistributions of source code must retain the above copyright
//    notice, this list of conditions and the following disclaimer.
//  * Redistributions in binary form must reproduce the above copyright
//    notice, this list of conditions and the following disclaimer in the
//    documentation and/or other materials provided with the distribution.
//  * Neither the name of NVIDIA CORPORATION nor the names of its
//    contributors may be used to endorse or promote products derived
//    from this software without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ``AS IS'' AND ANY
// EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
// IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
// PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
// CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
// EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
// PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
// PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
// OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
// OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
//
//----------------------------------------------------------------------------------
