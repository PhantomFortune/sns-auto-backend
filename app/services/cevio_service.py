"""
CeVIO AI Service
Handles text-to-speech using CeVIO AI via COM interface
"""
import logging
import platform
from typing import Optional

logger = logging.getLogger(__name__)

# Windows only - CeVIO AI uses COM interface
if platform.system() == "Windows":
    try:
        import win32com.client
        COM_AVAILABLE = True
    except ImportError:
        COM_AVAILABLE = False
        logger.warning("pywin32 is not installed. CeVIO AI functionality will be disabled.")
else:
    COM_AVAILABLE = False
    logger.warning("CeVIO AI is only available on Windows.")


class CeVIOService:
    """Service for CeVIO AI text-to-speech"""
    
    def __init__(self):
        self.talker = None
        self.is_connected = False
        self.com_available = COM_AVAILABLE
        
        if not self.com_available:
            logger.warning("CeVIO AI service is not available (not Windows or pywin32 not installed)")
    
    def ensure_connected(self) -> bool:
        """
        Ensure CeVIO AI is connected. Try to connect if not connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        if not self.com_available:
            logger.error("COM interface is not available")
            return False
        
        # If already connected, verify it's still working
        if self.is_connected and self.talker:
            try:
                # Try to access a property to verify connection
                _ = self.talker.Cast
                return True
            except Exception as e:
                logger.warning(f"CeVIO AI connection lost, reconnecting: {e}")
                self.talker = None
                self.is_connected = False
        
        # Try to connect
        if not self.is_connected:
            try:
                # Connect to CeVIO AI via COM
                # Try different ProgIDs in case the exact one differs
                # CeVIO AIのCOMインターフェースの正しいProgIDを試行
                prog_ids = [
                    "CeVIO.Talk.RemoteService2.Talker2V40",  # CeVIO AI ver9.1.17.0用
                    "CeVIO.Talk.RemoteService2.ServiceControl2V40",  # サービス制御用
                    "CeVIO.Talk.RemoteService2",
                    "CeVIO.Talk.RemoteService",
                ]
                
                for prog_id in prog_ids:
                    try:
                        logger.info(f"Attempting to connect to CeVIO AI with ProgID: {prog_id}")
                        self.talker = win32com.client.Dispatch(prog_id)
                        
                        # Test connection by trying to access a property
                        # For Talker interface, try Cast property
                        # For ServiceControl interface, we might need different approach
                        try:
                            # Try to access Cast property (Talker interface)
                            test_cast = self.talker.Cast
                            logger.debug(f"Successfully accessed Cast property with {prog_id} (current: {test_cast})")
                            self.is_connected = True
                            logger.info(f"CeVIO AI service connected successfully using {prog_id}")
                            return True
                        except AttributeError:
                            # Cast property doesn't exist - might be ServiceControl interface
                            logger.debug(f"Cast property not found for {prog_id}, might be ServiceControl interface")
                            # Try to get Talker from ServiceControl
                            try:
                                if hasattr(self.talker, 'GetTalker'):
                                    self.talker = self.talker.GetTalker()
                                    _ = self.talker.Cast
                                    self.is_connected = True
                                    logger.info(f"CeVIO AI service connected via ServiceControl using {prog_id}")
                                    return True
                                else:
                                    logger.debug(f"GetTalker method not found for {prog_id}")
                                    continue
                            except Exception as e:
                                logger.debug(f"Could not get Talker from ServiceControl: {e}")
                                continue
                        except Exception as e:
                            logger.debug(f"Error testing connection with {prog_id}: {e}")
                            continue
                    except Exception as e:
                        logger.debug(f"Failed to create COM object with {prog_id}: {e}")
                        continue
                
                # If all ProgIDs failed, log error
                logger.error("Failed to connect to CeVIO AI with any known ProgID. Make sure CeVIO AI is running.")
                self.talker = None
                self.is_connected = False
                return False
                
            except Exception as e:
                logger.error(f"Failed to initialize CeVIO AI service: {e}", exc_info=True)
                self.talker = None
                self.is_connected = False
                return False
        
        return True
    
    def speak(self, text: str, cast: str = "フィーちゃん") -> bool:
        """
        Speak text using CeVIO AI
        
        Args:
            text: Text to speak
            cast: Voice cast name (フィーちゃん, ユニちゃん, 夏色花梨)
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Ensure connection before speaking
        if not self.ensure_connected():
            logger.error("CeVIO AI is not connected. Please make sure CeVIO AI is running.")
            return False
        
        try:
            # Stop any current speech first
            try:
                self.talker.Stop()
            except Exception as e:
                logger.debug(f"Could not stop current speech (may not be speaking): {e}")
            
            # Set cast (キャスト)
            # CeVIO AIのCOMインターフェースに応じて調整が必要な場合があります
            cast_set = False
            try:
                self.talker.Cast = cast
                cast_set = True
                logger.debug(f"Set cast to {cast} using Cast property")
            except AttributeError:
                # Castプロパティが存在しない場合、別の方法を試す
                try:
                    self.talker.SetCast(cast)
                    cast_set = True
                    logger.debug(f"Set cast to {cast} using SetCast method")
                except Exception as e:
                    logger.warning(f"Could not set cast to {cast}: {e}. Using default cast.")
            except Exception as e:
                logger.warning(f"Error setting cast to {cast}: {e}. Using default cast.")
            
            # Set text to speak
            try:
                self.talker.Text = text
            except Exception as e:
                logger.error(f"Error setting text: {e}")
                raise
            
            # Start speaking (非同期)
            try:
                self.talker.Play()
            except Exception as e:
                logger.error(f"Error starting playback: {e}")
                raise
            
            logger.info(f"CeVIO AI speaking: {text[:50]}... (cast: {cast})")
            return True
            
        except Exception as e:
            logger.error(f"Error speaking with CeVIO AI: {e}", exc_info=True)
            # Connection might be lost, reset it
            self.is_connected = False
            self.talker = None
            return False
    
    def stop(self) -> bool:
        """
        Stop current speech
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        try:
            self.talker.Stop()
            logger.info("CeVIO AI speech stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping CeVIO AI speech: {e}")
            return False
    
    def is_speaking(self) -> bool:
        """
        Check if currently speaking
        
        Returns:
            bool: True if speaking, False otherwise
        """
        if not self.ensure_connected():
            return False
        
        try:
            return bool(self.talker.IsPlaying)
        except AttributeError:
            # IsPlayingプロパティが存在しない場合
            try:
                return bool(self.talker.GetIsPlaying())
            except:
                return False
        except Exception as e:
            logger.error(f"Error checking CeVIO AI speaking status: {e}")
            return False
    
    def get_available_casts(self) -> list[str]:
        """
        Get list of available voice casts
        
        Returns:
            list[str]: List of available cast names
        """
        # Default casts - these are the standard CeVIO AI Talk voices
        default_casts = ["フィーちゃん", "ユニちゃん", "夏色花梨"]
        
        if not self.ensure_connected():
            # Return default casts even if not connected
            return default_casts
        
        try:
            # Try to get available casts from CeVIO AI
            # Note: The actual API may differ, so we return defaults for now
            # If CeVIO AI provides a method to enumerate casts, it can be added here
            return default_casts
        except Exception as e:
            logger.error(f"Error getting available casts: {e}")
            return default_casts


# Global service instance
cevio_service = CeVIOService()

