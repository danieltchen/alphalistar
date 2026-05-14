"""
processor_nlp.py - Class for chunking, tokenizing, and embedding unstructured text data from press releases and mdna sections
from filings. Using OpenAI API text-embedding-3-small for embedding
"""

import os
import re
from typing import List, Optional
import nltk
import tiktoken
from openai import AsyncOpenAI
import logging
from dataclasses import dataclass
from typing import TypeVar, Generic

T = TypeVar("T")

# Setup logging
logger = logging.getLogger(__name__)

@dataclass
class ProcessedChunk(Generic[T]):
    """Data class to hold processed chunk information"""

    chunk_number: int
    text: str
    embedding: List[float]
    metadata: Optional[T] = None


def safe_sent_tokenize(text: str) -> List[str]:
    """Safe sentence tokenization with fallback."""
    try:
        # Type cast to satisfy mypy - we know nltk.sent_tokenize returns List[str]
        sentences: List[str] = list(nltk.sent_tokenize(text))
        return sentences
    except Exception as e:
        logging.warning(f"NLTK tokenization failed, using regex fallback: {e}")
        # Simple regex-based sentence tokenizer as fallback
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [s.strip() for s in sentences if s.strip()]


class NlpProcessor:
    """Class for processing text using NLP techniques including chunking, tokenization, and embedding."""

    def __init__(
        self, openai_client: AsyncOpenAI, model: str = "gpt-4.1-mini-2025-04-14"
    ):
        """
        Initialize NLP processor with necessary components.

        Args:
            openai_client: AsyncOpenAI client instance
            model: Model to use for tokenization
            (default model: "gpt-4.1-mini-2025-04-14")
        """
        self.client = openai_client
        self.model = model
        self.encoding = tiktoken.get_encoding("cl100k_base")

        # Initialize NLTK with better error handling
        self._setup_nltk()

    def _setup_nltk(self) -> None:
        """Setup NLTK with comprehensive fallback strategies."""
        try:
            # First try to find existing tokenizers
            for resource in ["tokenizers/punkt_tab", "tokenizers/punkt"]:
                try:
                    nltk.data.find(resource)
                    logger.info(f"NLTK resource found: {resource}")
                    return
                except LookupError:
                    continue

            # If no tokenizers found, try to download them
            logger.warning("No NLTK tokenizers found, attempting download")

            nltk_data_dir = "/tmp/nltk_data"
            os.makedirs(nltk_data_dir, exist_ok=True)
            nltk.data.path.insert(0, nltk_data_dir)

            # Try to download both old and new punkt resources
            download_success = False
            for resource in ["punkt_tab", "punkt"]:
                try:
                    nltk.download(resource, download_dir=nltk_data_dir, quiet=True)
                    logger.info(f"Successfully downloaded {resource}")
                    download_success = True
                    break
                except Exception as e:
                    logger.warning(f"Failed to download {resource}: {e}")

            if not download_success:
                logger.warning(
                    "Failed to download NLTK resources, will use regex fallback"
                )

        except Exception as e:
            logger.error(f"Error setting up NLTK: {e}")
            logger.warning("Will use regex fallback for sentence tokenization")

    def chunk_text(self, text: str, token_count: int) -> List[str]:
        """
        Split text into chunks based on token count with sentence awareness.

        Args:
            text: Input text to chunk
            token_count: Maximum tokens per chunk

        Returns:
            List of text chunks
        """
        # Calculate overlap as 10% of token_count and ensure it's an integer
        overlap = int(token_count * 0.1)

        try:
            # sentences = nltk.sent_tokenize(text)
            sentences = safe_sent_tokenize(text)
            chunks: List[str] = []
            token_buffer: List[int] = []

            for sentence in sentences:
                sentence_tokens = self.encoding.encode(sentence)

                # Check if adding sentence would exceed token limit
                if (
                    len(token_buffer) + len(sentence_tokens) > token_count
                    and token_buffer
                ):
                    # Create chunk from current buffer
                    chunk = self.encoding.decode(token_buffer)
                    if chunk.strip():
                        chunks.append(chunk)
                    # Reset buffer with overlap - ensure we're using integer indices
                    token_buffer = token_buffer[-overlap:] if overlap > 0 else []

                token_buffer.extend(sentence_tokens)

            # Handle remaining text
            if token_buffer:
                final_chunk = self.encoding.decode(token_buffer)
                if final_chunk.strip():
                    chunks.append(final_chunk)

            logger.info(f"Created {len(chunks)} chunks from input text")
            return chunks

        except Exception as e:
            logger.error(f"Error in chunking text: {str(e)}")
            raise

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using OpenAI API.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector as list of floats
        """
        try:
            response = await self.client.embeddings.create(
                input=[text],
                model="text-embedding-3-small",
                encoding_format="float",
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise

    async def process_text(
        self, text: str, token_count: int, metadata: Optional[T] = None
    ) -> List[ProcessedChunk[T]]:
        """
        Process text through chunking and embedding generation.

        Args:
            text: Input text to process
            token_count: Maximum tokens per chunk
            metadata: Optional metadata to associate with chunks

        Returns:
            List of ProcessedChunk objects containing chunk information
        """
        try:
            # Clean text
            cleaned_text = self._clean_text(text)

            # Generate chunks
            chunks = self.chunk_text(cleaned_text, token_count)

            # Process each chunk
            processed_chunks: List[ProcessedChunk[T]] = []

            for i, chunk in enumerate(chunks, 1):
                embedding = await self.generate_embedding(chunk)
                processed_chunk = ProcessedChunk(
                    chunk_number=i,
                    text=chunk,
                    embedding=embedding,
                    metadata=metadata,
                )
                processed_chunks.append(processed_chunk)

            logger.info(f"Successfully processed {len(processed_chunks)} chunks")
            return processed_chunks

        except Exception as e:
            logger.error(f"Error in text processing: {str(e)}")
            raise

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Clean text before processing.

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove extra whitespace
        cleaned = " ".join(text.split())
        return cleaned
