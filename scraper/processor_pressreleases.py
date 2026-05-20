"""
processor_press_release.py - Class for processing press releases from 8-K and management discussion and analysis from 10-K filings
"""

from typing import Dict, Any, Optional
import logging
import re
import time
import asyncio
import html

# from edgar import Company, set_identity
from openai import AsyncOpenAI

# Import from our wrapper instead of directly from edgar
try:
    from .edgar_wrapper import Company, set_identity # type: ignore
except ImportError:
    from edgar_wrapper import Company, set_identity # type: ignore


try:
    from .connector_database import DatabaseConnector, is_edgar_eligible
    from .processor_financials import _safe_company
    from .processor_nlp import NlpProcessor
except ImportError:
    from connector_database import DatabaseConnector, is_edgar_eligible  # type: ignore
    from processor_financials import _safe_company  # type: ignore
    from processor_nlp import NlpProcessor  # type: ignore


class PressReleaseProcessor(DatabaseConnector):
    """Processor for extracting and storing press releases from 8-K filings."""

    def __init__(self, db_config: Dict[str, str], openai_client: AsyncOpenAI):
        """Initialize with database configuration."""
        super().__init__(db_config)
        self.nlp_processor = NlpProcessor(openai_client)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def clean_filing_text(text: str) -> str:
        """Clean and preprocess filing text."""
        if not text:
            return ""

        cleaned = text.strip()
        cleaned = " ".join(cleaned.split())
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"[^\w\s.,!?-]", " ", cleaned)
        cleaned = " ".join(cleaned.split())

        return cleaned

    @staticmethod
    def text_to_markdown(text: str) -> str:
        """
        Convert raw filing text to a more readable markdown format.
        This preserves paragraphs, adds proper spacing after punctuation, and formats
        headings, lists, tables, and other structured content.
        """
        if not text:
            return ""

        # First decode any HTML entities
        text = html.unescape(text)

        # Remove excessive whitespace but preserve paragraph breaks
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

        # Process each paragraph
        formatted_paragraphs = []
        in_table = False
        table_rows: list[str] = []

        for p in paragraphs:
            # Skip processing if empty
            if not p.strip():
                continue

            # Check if this might be a table row
            # Look for patterns like "| data | data |" or "data    data    data" (aligned columns)
            is_table_row = bool(re.search(r"(\|.*\|)|(\S+\s{2,}\S+\s{2,}\S+)", p))

            # Start or continue a table
            if is_table_row:
                if not in_table:
                    in_table = True
                    table_rows = []

                # Clean up and standardize table row format
                row = p.strip()

                # For space-separated "tables", convert to pipe format
                if not "|" in row:
                    # Convert multiple spaces to a single delimiter
                    cells = re.split(r"\s{2,}", row)
                    row = "| " + " | ".join(cells) + " |"

                table_rows.append(row)
                continue

            # End table if we were in one
            if in_table:
                # Format the collected table rows
                table_markdown = []

                # Add the rows
                for i, row in enumerate(table_rows):
                    table_markdown.append(row)

                    # Add separator row after the header (first row)
                    if i == 0:
                        # Count the number of columns by counting pipe characters
                        num_columns = row.count("|") - 1
                        separator = "| " + " | ".join(["---"] * num_columns) + " |"
                        table_markdown.append(separator)

                formatted_paragraphs.append("\n".join(table_markdown))
                in_table = False

            # Check for numbered lists (1. 2. 3. etc.)
            if re.match(r"^\s*\d+\.\s", p):
                # Split the paragraph into lines
                lines = p.split("\n")
                list_items = []

                for line in lines:
                    # Keep the existing numbering
                    list_items.append(line.strip())

                formatted_paragraphs.append("\n".join(list_items))
                continue

            # Check for bullet lists (• - * etc.)
            if re.match(r"^\s*[•\-\*]\s", p):
                # Split the paragraph into lines
                lines = p.split("\n")
                list_items = []

                for line in lines:
                    # Standardize to markdown bullet format
                    line = re.sub(r"^\s*[•\-\*]\s*", "- ", line)
                    list_items.append(line.strip())

                formatted_paragraphs.append("\n".join(list_items))
                continue

            # Process regular paragraph
            p_clean = re.sub(r"\s+", " ", p).strip()

            # Add spacing after punctuation if missing
            p_clean = re.sub(r"([.,!?:;])([^\s\d])", r"\1 \2", p_clean)

            # Format headings based on patterns
            if p_clean.isupper():
                # ALL CAPS text is likely a major heading
                p_clean = f"## {p_clean}"
            elif len(p_clean) < 80 and p_clean.endswith(":"):
                # Lines ending with colon are likely subheadings
                p_clean = f"### {p_clean}"
            elif re.match(r"^[A-Z][a-z]+\s+\d+(\.|:)", p_clean):
                # Patterns like "Section 1:" or "Item 7."
                p_clean = f"### {p_clean}"

            # Check for code blocks (indented text, often in technical sections)
            if re.match(r"^\s{4,}", p):
                lines = p.split("\n")
                if all(re.match(r"^\s{4,}", line) for line in lines if line.strip()):
                    code_lines = [line.strip() for line in lines]
                    p_clean = "```\n" + "\n".join(code_lines) + "\n```"

            formatted_paragraphs.append(p_clean)

        # Handle any remaining table at the end
        if in_table:
            table_markdown = []
            for i, row in enumerate(table_rows):
                table_markdown.append(row)
                if i == 0:
                    num_columns = row.count("|") - 1
                    separator = "| " + " | ".join(["---"] * num_columns) + " |"
                    table_markdown.append(separator)

            formatted_paragraphs.append("\n".join(table_markdown))

        # Join paragraphs with double line breaks for markdown
        markdown_text = "\n\n".join(formatted_paragraphs)

        return markdown_text

    @staticmethod
    def extract_press_release_title(content: str) -> str:
        """Extract a meaningful title from press release content."""
        lines = [line.strip() for line in content.split("\n") if line.strip()]

        for line in lines:
            line_lower = line.lower()
            if len(line) > 20 and not any(
                header in line_lower
                for header in [
                    "for immediate release",
                    "press release",
                    "news release",
                    "exhibit 99",
                    "exhibit 99.1",
                ]
            ):
                return line[:200]

        return "Press Release"

    @staticmethod
    def _available_section_keys(filing_obj: Any) -> set[str]:
        """Best-effort discovery of section keys from newer edgartools parsers."""
        keys: set[str] = set()

        sections_attr = getattr(filing_obj, "sections", None)
        if callable(sections_attr):
            try:
                sections_attr = sections_attr()
            except Exception:
                sections_attr = None

        if isinstance(sections_attr, dict):
            keys.update(str(k) for k in sections_attr.keys())
        elif isinstance(sections_attr, (list, tuple, set)):
            for item in sections_attr:
                if isinstance(item, str):
                    keys.add(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("key")
                    if name:
                        keys.add(str(name))

        return keys

    @staticmethod
    def _normalize_item_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    def _available_items(self, filing_obj: Any) -> set[str]:
        """Read item labels exposed by TenK/TenQ objects."""
        items = getattr(filing_obj, "items", None)
        if items is None:
            return set()
        if callable(items):
            try:
                items = items()
            except Exception:
                items = []

        normalized: set[str] = set()
        if isinstance(items, (list, tuple, set)):
            for item in items:
                normalized.add(self._normalize_item_key(str(item)))
        return normalized

    def _resolve_mdna_sections(
        self, filing_obj: Any, form_type: str
    ) -> list[tuple[str, str, list[str]]]:
        """
        Return section lookup tuples:
        (logical_section_id, section_title, candidate_keys_to_fetch)
        """
        section_map = {
            "10-K": [
                (
                    "Item 7",
                    "Management's Discussion and Analysis",
                    ["Item 7", "ITEM 7", "item 7", "part_ii_item_7", "item_7"],
                ),
                (
                    "Item 7A",
                    "Quantitative and Qualitative Disclosures About Market Risk",
                    ["Item 7A", "ITEM 7A", "item 7a", "part_ii_item_7a", "item_7a"],
                ),
            ],
            "10-Q": [
                (
                    "Item 2",
                    "Management's Discussion and Analysis of Financial Condition and Results of Operations",
                    ["Item 2", "ITEM 2", "item 2", "part_i_item_2", "item_2"],
                )
            ],
        }

        available_items = self._available_items(filing_obj)
        resolved: list[tuple[str, str, list[str]]] = []

        for logical_id, title, candidates in section_map.get(form_type, []):
            if not available_items:
                resolved.append((logical_id, title, candidates))
                continue

            matching_candidates = [
                candidate
                for candidate in candidates
                if self._normalize_item_key(candidate) in available_items
            ]
            if matching_candidates:
                resolved.append((logical_id, title, matching_candidates + candidates))

        return resolved

    def _get_section_content(self, filing_obj: Any, section_candidates: list[str]) -> Optional[str]:
        """Fetch first available section content from candidate keys."""
        for key in section_candidates:
            try:
                content = filing_obj[key]
                if content:
                    return str(content)
            except Exception:
                continue
        return None

    def check_filing_exists(self, conn: Any, accession_no: str) -> Optional[int]:
        """
        Check if a filing already exists and return its ID.
        Returns None if filing doesn't exist, or the filing ID if it exists.
        """
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, completed FROM FILING WHERE accessionNo = %s",
                (accession_no,),
            )
            result = cur.fetchone()
            if result is None:
                return None

            # Explicitly cast the result to int to satisfy mypy
            filing_id: int = int(result[0])
            return filing_id

    def check_filing_completed(self, conn: Any, accession_no: str) -> bool:
        """
        Check if a filing is completed.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM FILING 
                    WHERE accessionNo = %s AND completed = TRUE
                )
                """,
                (accession_no,),
            )
            result = cur.fetchone()

            # EXISTS always returns a boolean, never NULL
            return bool(result[0]) if result else False

    async def process_press_release(
        self, conn: Any, filing_id: int, press_release: Any, filing_info: Any
    ) -> None:
        """Process and store press release content from 8-K filing."""
        try:
            content = None

            # Extract content from attachments - specifically looking for EX-99.1
            if hasattr(press_release, "attachments") and press_release.attachments:
                for attachment in press_release.attachments:
                    # Look for press release exhibits (EX-99.1, etc.)
                    if (
                        hasattr(attachment, "document_type")
                        and attachment.document_type
                        and "EX-99" in attachment.document_type
                    ):

                        if hasattr(attachment, "text") and callable(attachment.text):
                            content = attachment.text()
                            self.logger.info(
                                f"Extracted content from {attachment.document_type} - length: {len(content)}"  # type: ignore[attr-defined]
                            )
                            break

            # Fallback: try any attachment if no EX-99 found
            if (
                not content
                and hasattr(press_release, "attachments")
                and press_release.attachments
            ):
                attachment = press_release.attachments[0]  # Use first attachment
                if hasattr(attachment, "text") and callable(attachment.text):
                    content = attachment.text()
                    self.logger.info(
                        f"Extracted content from first attachment - length: {len(content)}"  # type: ignore[attr-defined]
                    )

            if not content:
                self.logger.warning(
                    f"No press release content found for filing {filing_info.accession_no}"
                )
                return

            content_str = str(content)
            cleaned_content = self.clean_filing_text(content_str)
            title = self.extract_press_release_title(cleaned_content)

            # Process content using NLP processor
            processed_chunks = await self.nlp_processor.process_text(
                cleaned_content,
                token_count=500,
                metadata={
                    "filing_id": filing_id,
                    "accession_no": filing_info.accession_no,
                },
            )

            with conn.cursor() as cur:
                for chunk in processed_chunks:
                    query = """
                    INSERT INTO STATEMENTS 
                    (filingId, section, title, content, raw_content, markdown_content, word_count, 
                    chunk_number, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (filingId, section, chunk_number) 
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        raw_content = EXCLUDED.raw_content,
                        markdown_content = EXCLUDED.markdown_content,
                        word_count = EXCLUDED.word_count,
                        embedding = EXCLUDED.embedding::vector,
                        processed_date = CURRENT_TIMESTAMP
                    """

                    raw_content = chunk.text
                    cleaned_content = self.clean_filing_text(raw_content)
                    markdown_content = self.text_to_markdown(raw_content)
                    embedding_str = f"[{','.join(map(str, chunk.embedding))}]"

                    cur.execute(
                        query,
                        (
                            filing_id,
                            f"8-K PR_chunk_{chunk.chunk_number}",
                            title,
                            cleaned_content,
                            raw_content,
                            markdown_content,
                            len(cleaned_content.split()),
                            chunk.chunk_number,
                            embedding_str,
                        ),
                    )

            conn.commit()
            self.logger.info(
                f"Successfully stored press release for filing {filing_info.accession_no}"
            )

        except Exception as e:
            self.logger.error(
                f"Error processing press release for filing {filing_info.accession_no}: {str(e)}"
            )
            conn.rollback()
            raise

    async def process_eightk_filings(
        self,
        conn: Any,
        company: Company,
        ticker_id: int,
        symbol: str,
        limit_8k: int,
    ) -> None:
        """Process press releases from form 8-Ks for a company with specified limit."""
        try:
            latest_8ks = company.get_filings(form="8-K")
            filing_list = latest_8ks.latest(limit_8k)

            # Check if filing_list is None or not iterable
            if filing_list is None or not hasattr(filing_list, "__iter__"):
                if isinstance(
                    filing_list, object
                ):  # If it's a single EntityFiling object
                    filing_list = [filing_list]  # Convert to list with single item
                else:
                    self.logger.warning(f"No 8-K filings retrieved for {symbol}")
                    return

            self.logger.info(f"Retrieved {len(filing_list)} 8-K filings for {symbol}")

            for filing in filing_list:
                try:
                    self.logger.info(f"Processing filing {filing.accession_no}")  # type: ignore[attr-defined]

                    # Check if filing already exists and is completed
                    if self.check_filing_completed(conn, filing.accession_no):  # type: ignore[attr-defined]
                        self.logger.info(
                            f"Filing {filing.accession_no} already processed completely, skipping"  # type: ignore[attr-defined]
                        )
                        continue

                    filing_obj = filing.obj()  # type: ignore[attr-defined]

                    if (
                        not hasattr(filing_obj, "has_press_release")
                        or not filing_obj.has_press_release
                    ):
                        self.logger.info(
                            f"Filing {filing.accession_no} has no press release"  # type: ignore[attr-defined]
                        )
                        continue

                    self.logger.info(
                        f"Found press release in filing {filing.accession_no}"  # type: ignore[attr-defined]
                    )

                except AttributeError as e:
                    self.logger.error(
                        f"Filing object has unexpected structure: {str(e)}"
                    )
                    continue
                except Exception as e:
                    self.logger.error(f"Error processing individual filing: {str(e)}")
                    continue

                try:
                    # Check if filing exists but is not completed
                    filing_id = self.check_filing_exists(conn, filing.accession_no)  # type: ignore[attr-defined]
                    if filing_id is None:
                        # Insert new filing record
                        filing_id = self.insert_filing_record(
                            conn, ticker_id, symbol, filing
                        )

                    await self.process_press_release(
                        conn, filing_id, filing_obj.press_releases, filing
                    )

                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE FILING SET completed = TRUE WHERE id = %s",
                            (filing_id,),
                        )
                        conn.commit()

                    self.logger.info(
                        f"Successfully processed filing {filing.accession_no}"  # type: ignore[attr-defined]
                    )

                except Exception as e:
                    self.logger.error(
                        f"Error processing individual filing {filing.accession_no}: {str(e)}"  # type: ignore[attr-defined]
                    )
                    continue

                time.sleep(1)  # Rate limiting

        except Exception as e:
            self.logger.error(f"Error processing press releases for {symbol}: {str(e)}")
            raise

    async def process_company(
        self, ticker: str, limit_8k: int, limit_10k: int, limit_10q: Optional[int] = None
    ) -> None:
        """Process press releases for a single company."""
        symbol = ticker.upper()
        ticker_id = self.get_ticker_id(symbol)
        tenq_limit = limit_10q if limit_10q is not None else limit_10k
        
        company = _safe_company(symbol)
        if company is None:
            self.logger.warning(
                "[press releases] EDGAR could not resolve %s; skipping", symbol
            )
            return

        with self.get_db_connection() as conn:
            try:
                await self.process_eightk_filings(
                    conn, company, ticker_id, symbol, limit_8k
                )
                await asyncio.sleep(1)  # Rate limiting between companies

                await self.process_mdna_sections(
                    conn, company, ticker_id, symbol, limit_10k, form_type="10-K"
                )
                await asyncio.sleep(1)

                await self.process_mdna_sections(
                    conn, company, ticker_id, symbol, tenq_limit, form_type="10-Q"
                )
                await asyncio.sleep(1)

                self.logger.info(f"Completed filings processing for {symbol}")

            except Exception as e:
                self.logger.error(
                    f"Error processing filings for company {symbol}: {str(e)}"
                )

        self.logger.info(f"Press release processing completed for {symbol}")            
                

    async def process_companies(
        self, limit_8k: int, limit_10k: int, limit_10q: Optional[int] = None
    ) -> None:
        """Process press releases for all companies."""
        tickers = self.get_tickers()
        self.logger.info(f"Found {len(tickers)} tickers to process")
        tenq_limit = limit_10q if limit_10q is not None else limit_10k

        with self.get_db_connection() as conn:
            for ticker in tickers:
                symbol = ticker["symbol"]
                ticker_id = ticker["id"]
                self.logger.info(f"Processing {symbol}")

                if not is_edgar_eligible(ticker.get("quote_type")):
                    self.logger.info(
                        "[press releases] %s quote_type=%s; skipping EDGAR",
                        symbol,
                        ticker.get("quote_type"),
                    )
                    continue

                company = _safe_company(symbol)
                if company is None:
                    continue

                try:
                    await self.process_eightk_filings(
                        conn, company, ticker_id, symbol, limit_8k
                    )
                    await asyncio.sleep(1)  # Rate limiting between companies

                    await self.process_mdna_sections(
                        conn, company, ticker_id, symbol, limit_10k, form_type="10-K"
                    )
                    await asyncio.sleep(1)

                    await self.process_mdna_sections(
                        conn, company, ticker_id, symbol, tenq_limit, form_type="10-Q"
                    )
                    await asyncio.sleep(1)

                    self.logger.info(f"Completed filings processing for {symbol}")

                except Exception as e:
                    self.logger.error(
                        f"Error processing filings for company {symbol}: {str(e)}"
                    )
                    continue

        self.logger.info("Press release processing completed")

    async def process_mdna_sections(
        self,
        conn: Any,
        company: Company,
        ticker_id: int,
        symbol: str,
        filing_limit: int,
        form_type: str = "10-K",
    ) -> None:
        """Process MD&A sections from 10-K / 10-Q filings."""
        latest_filings = company.get_filings(form=form_type)
        filing_list = latest_filings.latest(filing_limit)

        # Check if filing_list is None or not iterable
        if filing_list is None or not hasattr(filing_list, "__iter__"):
            if isinstance(filing_list, object):  # If it's a single EntityFiling object
                filing_list = [filing_list]  # Convert to list with single item
            else:
                self.logger.warning(f"No {form_type} filings retrieved for {symbol}")
                return

        self.logger.info(f"Retrieved {len(filing_list)} {form_type} filings for {symbol}")

        for filing in filing_list:
            try:
                # Check if filing already exists and is completed
                if self.check_filing_completed(conn, filing.accession_no):  # type: ignore[attr-defined]
                    self.logger.info(
                        f"Filing {filing.accession_no} already processed completely, skipping"  # type: ignore[attr-defined]
                    )
                    continue

                self.logger.info(
                    f"Processing MDNA for {form_type} filing {filing.accession_no}"
                ) # type: ignore[attr-defined]

                # Check if filing exists but is not completed
                filing_id = self.check_filing_exists(conn, filing.accession_no)  # type: ignore[attr-defined]
                if filing_id is None:
                    # Insert new filing record
                    filing_id = self.insert_filing_record(
                        conn, ticker_id, symbol, filing
                    )

                did_store_mdna = await self.process_mdna_section(
                    filing, filing_id, form_type
                )
                if did_store_mdna:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE FILING SET completed = TRUE WHERE id = %s",
                            (filing_id,),
                        )
                        conn.commit()
                    self.logger.info(
                        f"Successfully processed MDNA for {form_type} filing {filing.accession_no}"  # type: ignore[attr-defined]
                    )
                else:
                    self.logger.warning(
                        f"No MD&A content stored for {form_type} filing {filing.accession_no}; leaving completed=FALSE for retry"  # type: ignore[attr-defined]
                    )
                time.sleep(1)

            except AttributeError as e:
                self.logger.error(f"Filing object has unexpected structure: {str(e)}")
                continue
            except Exception as e:
                self.logger.error(
                    f"Error processing MDNA for filing {filing.accession_no}: {str(e)}"  # type: ignore[attr-defined]
                )
                conn.rollback()
                continue

    async def process_mdna_section(self, filing: Any, filing_id: int, form_type: str) -> bool:
        """Process and store the MD&A sections from a TenK/TenQ filing."""
        with self.get_db_connection() as conn:
            try:
                filing_obj = filing.obj()
                sections = self._resolve_mdna_sections(filing_obj, form_type=form_type)
                if not sections:
                    self.logger.warning(
                        f"No compatible MD&A sections discovered for {form_type} filing {filing.accession_no}"
                    )
                    return False

                stored_any = False

                for logical_section_id, section_title, section_candidates in sections:
                    try:
                        content = self._get_section_content(filing_obj, section_candidates)
                        if not content:
                            self.logger.warning(
                                f"No content found for {logical_section_id} in {form_type} filing {filing.accession_no}"
                            )
                            continue

                        cleaned_content = self.clean_filing_text(content)
                        if not cleaned_content:
                            self.logger.warning(
                                f"Empty content after cleaning for {section_key} in filing {filing.accession_no}"
                            )
                            continue

                        # Process content using NLP processor
                        processed_chunks = await self.nlp_processor.process_text(
                            cleaned_content,
                            token_count=500,
                            metadata={
                                "filing_id": filing_id,
                                "accession_no": filing.accession_no,
                            },
                        )

                        with conn.cursor() as cur:
                            for chunk in processed_chunks:
                                query = """
                                INSERT INTO STATEMENTS 
                                (filingId, section, title, content, raw_content, markdown_content, word_count, chunk_number, embedding)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                                ON CONFLICT (filingId, section, chunk_number) 
                                DO UPDATE SET
                                    content = EXCLUDED.content,
                                    raw_content = EXCLUDED.raw_content,
                                    markdown_content = EXCLUDED.markdown_content,
                                    word_count = EXCLUDED.word_count,
                                    embedding = EXCLUDED.embedding::vector,
                                    processed_date = CURRENT_TIMESTAMP
                                """

                                # Save the raw content before cleaning
                                raw_content = chunk.text

                                # Clean the content for embedding purposes
                                cleaned_content = self.clean_filing_text(raw_content)

                                # Generate markdown from the raw content
                                markdown_content = self.text_to_markdown(raw_content)

                                # Convert embedding list to a string format that pgvector expects
                                embedding_str = (
                                    f"[{','.join(map(str, chunk.embedding))}]"
                                )

                                # Convert embedding list to a string format that pgvector expects
                                embedding_str = (
                                    f"[{','.join(map(str, chunk.embedding))}]"
                                )

                                cur.execute(
                                    query,
                                    (
                                        filing_id,
                                        f"{logical_section_id}_chunk_{chunk.chunk_number}",
                                        section_title,
                                        cleaned_content,
                                        raw_content,
                                        markdown_content,
                                        len(chunk.text.split()),
                                        chunk.chunk_number,
                                        embedding_str,
                                    ),
                                )
                            conn.commit()
                            stored_any = True
                            self.logger.info(
                                f"Successfully stored mdna for filing {filing.accession_no}"
                            )

                    except Exception as e:
                        self.logger.error(
                            f"Error processing mdna {logical_section_id} for {form_type} filing {filing.accession_no}: {str(e)}"
                        )
                        continue

                return stored_any

            except Exception as e:
                self.logger.error(
                    f"Error in process_mdna_section for filing {filing.accession_no}: {str(e)}"
                )
                conn.rollback()
                raise
