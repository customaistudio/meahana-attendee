import httpx
from app.core.database import get_supabase
from app.core.config import settings
from typing import List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TranscriptService:
    async def fetch_full_transcript(
        self, 
        bot_id: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch full transcript from Attendee API"""
        
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Token {settings.attendee_api_key}",
                "Content-Type": "application/json",
            }
            
            try:
                api_url = f"{settings.attendee_api_base_url}/api/v1/bots/{bot_id}/transcript"
                
                response = await client.get(
                    api_url,
                    headers=headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Handle different response formats from Attendee API
                if isinstance(data, list):
                    # API returned transcript list directly
                    transcript_chunks = data
                elif isinstance(data, dict):
                    # API returned JSON object with transcript key
                    transcript_chunks = data.get("transcript", [])
                else:
                    logger.error(f"Unexpected response format from Attendee API: {type(data)}")
                    transcript_chunks = []
                
                # Process and store transcript chunks
                await self._process_transcript_chunks(bot_id, transcript_chunks, user_id)
                
                return transcript_chunks
                
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching transcript: {e}")
                raise
            except Exception as e:
                logger.error(f"Error fetching transcript: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise

    async def _process_transcript_chunks(
        self,
        bot_id: str,
        transcript_chunks: List[Dict[str, Any]],
        user_id: str
    ):
        """Process and store transcript chunks using Supabase"""
        
        try:
            supabase = get_supabase()
            
            # Get meeting by bot_id
            from app.services.bot_service import BotService
            meeting = await BotService.get_meeting_by_bot_id(bot_id, user_id)
            
            if not meeting:
                logger.error(f"Meeting not found for bot_id: {bot_id}")
                return
            
            processed_count = 0
            for chunk_data in transcript_chunks:
                try:
                    # Handle Attendee API response format
                    speaker = chunk_data.get("speaker_name") or chunk_data.get("speaker")
                    text = chunk_data.get("transcription", {}).get("transcript") or chunk_data.get("text")
                    timestamp_ms = chunk_data.get("timestamp_ms")
                    timestamp_str = chunk_data.get("timestamp")
                    
                    # Convert timestamp_ms to ISO format if available
                    if timestamp_ms and not timestamp_str:
                        timestamp_str = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
                    
                    # Better validation - check for None values before logging
                    if text is None:
                        logger.warning(f"Skipping chunk with None text: speaker={speaker}, timestamp={timestamp_str}")
                        continue
                        
                    if timestamp_str is None:
                        logger.warning(f"Skipping chunk with None timestamp: speaker={speaker}, text={text[:50] if text else 'None'}...")
                        continue
                    
                    if not text or not timestamp_str:
                        logger.warning(f"Skipping chunk with missing data: speaker={speaker}, text={text}, timestamp={timestamp_str}")
                        continue
                    
                    # Parse timestamp
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    
                    # Check if chunk already exists
                    result = supabase.table("transcript_chunks").select("*").eq("meeting_id", meeting["id"]).eq("user_id", user_id).eq("timestamp", timestamp.isoformat()).eq("speaker", speaker).execute()
                    
                    if result.error:
                        logger.error(f"Supabase error checking existing chunk: {result.error}")
                        continue
                    
                    existing_chunks = result.data
                    
                    if not existing_chunks:
                        # Create new chunk
                        chunk_data = {
                            "meeting_id": meeting["id"],
                            "user_id": user_id,
                            "speaker": speaker,
                            "text": text,
                            "timestamp": timestamp.isoformat()
                        }
                        
                        insert_result = supabase.table("transcript_chunks").insert(chunk_data).execute()
                        
                        if insert_result.error:
                            logger.error(f"Failed to insert transcript chunk: {insert_result.error}")
                        else:
                            processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing transcript chunk: {e}")
                    import traceback
                    logger.error(f"Chunk processing traceback: {traceback.format_exc()}")
                    continue
            
            logger.info(f"Processed {processed_count} transcript chunks for bot {bot_id}")
            
        except Exception as e:
            logger.error(f"Error in _process_transcript_chunks: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def get_transcript_chunks(
        self, 
        meeting_id: int,
        user_id: str
    ) -> List[Dict]:
        """Get transcript chunks for a meeting"""
        try:
            supabase = get_supabase()
            
            result = supabase.table("transcript_chunks").select("*").eq("meeting_id", meeting_id).eq("user_id", user_id).order("timestamp").execute()
            
            if result.error:
                logger.error(f"Supabase error: {result.error}")
                return []
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting transcript chunks: {e}")
            return []
    
    async def get_transcript_summary(
        self,
        meeting_id: int,
        user_id: str
    ) -> Dict[str, Any]:
        """Get a summary of transcript data for a meeting"""
        try:
            chunks = await self.get_transcript_chunks(meeting_id, user_id)
            
            if not chunks:
                return {
                    "total_chunks": 0,
                    "total_duration": 0,
                    "speakers": [],
                    "word_count": 0
                }
            
            # Calculate summary statistics
            total_chunks = len(chunks)
            speakers = list(set(chunk["speaker"] for chunk in chunks if chunk.get("speaker")))
            word_count = sum(len(chunk["text"].split()) for chunk in chunks if chunk.get("text"))
            
            # Estimate duration based on chunk count (rough approximation)
            total_duration = total_chunks * 10  # Assume 10 seconds per chunk
            
            return {
                "total_chunks": total_chunks,
                "total_duration": total_duration,
                "speakers": speakers,
                "word_count": word_count
            }
            
        except Exception as e:
            logger.error(f"Error getting transcript summary: {e}")
            return {} 