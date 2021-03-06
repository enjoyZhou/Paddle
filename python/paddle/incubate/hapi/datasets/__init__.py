#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from . import folder
from . import mnist
from . import flowers
from . import cifar
from . import voc2012
from . import conll05
from . import imdb
from . import imikolov
from . import movielens
from . import movie_reviews
from . import uci_housing
from . import wmt14
from . import wmt16

from .folder import *
from .mnist import *
from .flowers import *
from .cifar import *
from .voc2012 import *
from .conll05 import *
from .imdb import *
from .imikolov import *
from .movielens import *
from .movie_reviews import *
from .uci_housing import *
from .wmt14 import *
from .wmt16 import *

__all__ = folder.__all__ \
          + mnist.__all__ \
          + flowers.__all__ \
          + cifar.__all__ \
          + voc2012.__all__ \
          + conll05.__all__ \
          + imdb.__all__ \
          + imikolov.__all__ \
          + movielens.__all__ \
          + movie_reviews.__all__ \
          + uci_housing.__all__ \
          + wmt14.__all__ \
          + wmt16.__all__
