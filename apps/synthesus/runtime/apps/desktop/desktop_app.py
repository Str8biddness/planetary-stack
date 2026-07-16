import customtkinter as ctk
import asyncio
import os
import sys
import threading
from datetime import datetime

# Add synthesus_framework to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# Note: In the monorepo structure, synthesus_framework is in the same folder as this script.
SYNTH_FRAMEWORK = os.path.join(current_dir, "synthesus_framework")
if SYNTH_FRAMEWORK not in sys.path:
    sys.path.append(SYNTH_FRAMEWORK)

# Try importing the master
try:
    from core.quadbrain_master import QuadbrainMaster
    IMPORT_SUCCESS = True
except ImportError as e:
    print(f"Warning: Could not import QuadbrainMaster ({e}). Using mock.")
    IMPORT_SUCCESS = False
    class QuadbrainMaster:
        def __init__(self):
            self.shared_state = type('obj', (object,), {
                't': 0,
                'fluid': type('obj', (object,), {
                    'policy_prior': 0.5,
                    'risk_outcome': 0.1,
                    'attention': 0.5
                })
            })
        async def think(self, query, **kwargs):
            await asyncio.sleep(0.5)
            return {"answer": f"Mock Response: {query}"}

class GhostkeyDesktopApp(ctk.CTk):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop
        self.current_persona = "ghostkey"
        
        # Change to framework dir to ensure models/configs load correctly
        if IMPORT_SUCCESS:
            os.chdir(SYNTH_FRAMEWORK)
        
        self.master_ai = QuadbrainMaster()

        self.title("SYNTHESUS 4.0 - Multi-Persona Terminal")
        self.geometry("1100x700")
        
        # Theme
        ctk.set_appearance_mode("dark")
        self.theme_color = "#00ffcc"

        # Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="SYNTHESUS AI", 
                                      font=ctk.CTkFont(size=24, weight="bold", family="Consolas"))
        self.logo_label.pack(pady=30)

        # Persona Swapper
        self.persona_label = ctk.CTkLabel(self.sidebar, text="ACTIVE SUBSTRATE:", font=ctk.CTkFont(size=12))
        self.persona_label.pack(pady=(0, 5))
        self.persona_option = ctk.CTkOptionMenu(self.sidebar, values=["Ghostkey (Sentinel)", "Breach (Red-Team)"],
                                               command=self.change_persona)
        self.persona_option.pack(pady=(0, 20), padx=20)

        self.status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=20)

        self.mc_bar = self.create_metric_bar("Policy Prior (MC)", 0.5, "cyan")
        self.psi_bar = self.create_metric_bar("Attention (Psi)", 0.5, "magenta")
        self.ns_bar = self.create_metric_bar("Risk Analysis (NS)", 0.1, "red")

        # Hardware Info Display
        self.hw_label = ctk.CTkLabel(self.sidebar, text="HARDWARE PROFILE:", font=ctk.CTkFont(size=12))
        self.hw_label.pack(pady=(20, 5))
        self.hw_info = ctk.CTkLabel(self.sidebar, text="Sensing...", font=ctk.CTkFont(size=10, family="Consolas"), 
                                    text_color="gray", justify="left")
        self.hw_info.pack(padx=20)

        self.info_label = ctk.CTkLabel(self.sidebar, text="SYSTEM READY", text_color="green")
        self.info_label.pack(side="bottom", pady=20)

        # --- Main Chat Area ---
        self.chat_container = ctk.CTkFrame(self, fg_color="#1a1a1a")
        self.chat_container.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.chat_container.grid_columnconfigure(0, weight=1)
        self.chat_container.grid_rowconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.chat_container, state="disabled", 
                                          font=ctk.CTkFont(size=14, family="Consolas"),
                                          fg_color="#0d0d0d", text_color="#00ffcc")
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

        # Input Area
        self.input_frame = ctk.CTkFrame(self.chat_container, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.input_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Enter system directive...",
                                       height=45, font=ctk.CTkFont(size=14))
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.input_entry.bind("<Return>", lambda e: self.send_message())

        self.transmit_btn = ctk.CTkButton(self.input_frame, text="TRANSMIT", width=120, height=45,
                                         command=self.send_message, fg_color="#006666", hover_color="#008888")
        self.transmit_btn.grid(row=0, column=1)

        # Initial Boot Sequence
        self.append_chat("SYSTEM", "Initializing Quadbrain 4.0 Substrate...")
        self.append_chat("SYSTEM", "Secure Enclave: Local Memory Mode.")
        self.append_chat("GHOSTKEY", "Sentinel active. Awaiting instructions.")

        # Metrics update loop
        self.update_metrics_loop()

    def apply_persona_theme(self, persona):
        if persona == "ghostkey":
            self.theme_color = "#00ffcc" # Cyan-ish
            ctk.set_default_color_theme("blue")
        else:
            self.theme_color = "#ff3333" # Red
            ctk.set_default_color_theme("dark-blue")
        
        if hasattr(self, "chat_display"):
            self.chat_display.configure(text_color=self.theme_color)
        if hasattr(self, "transmit_btn"):
            self.transmit_btn.configure(fg_color=self.theme_color if persona == "breach" else "#006666")

    def change_persona(self, choice):
        new_persona = "ghostkey" if "Ghostkey" in choice else "breach"
        if new_persona == self.current_persona: return
        
        self.current_persona = new_persona
        self.apply_persona_theme(new_persona)
        
        self.append_chat("SYSTEM", f"Re-initializing Quadbrain Substrate: {new_persona.upper()}...")
        # Update current persona for AI think
        self.append_chat(new_persona.upper(), "Substrate synchronized. Awaiting mission parameters.")

    def create_metric_bar(self, label, initial_val, color):
        lbl = ctk.CTkLabel(self.status_frame, text=label, font=ctk.CTkFont(size=12, family="Consolas"))
        lbl.pack(pady=(15, 0), anchor="w")
        bar = ctk.CTkProgressBar(self.status_frame, progress_color=color)
        bar.set(initial_val)
        bar.pack(pady=5, fill="x")
        return bar

    def update_metrics_loop(self):
        try:
            # Handle both possible state attributes
            if hasattr(self.master_ai, "shared_state"):
                fluid = self.master_ai.shared_state.fluid
            elif hasattr(self.master_ai, "state"):
                fluid = self.master_ai.state.fluid
            else:
                fluid = None

            if fluid:
                self.mc_bar.set(getattr(fluid, "policy_prior", 0.5))
                self.psi_bar.set(getattr(fluid, "attention", 0.5))
                self.ns_bar.set(getattr(fluid, "risk_outcome", 0.1))

            # Update Hardware Info
            runtime = getattr(self.master_ai, "runtime", None)
            if runtime and hasattr(runtime, "_host_profile") and runtime._host_profile:
                cpu = runtime._host_profile.get("cpu", {})
                model = cpu.get("model", "Unknown")
                if len(model) > 25: model = model[:22] + "..."
                self.hw_info.configure(text=f"CPU: {model}\nCORES: {cpu.get('cores', 0)}\nFEATURES: {', '.join(cpu.get('features', [])[:3])}...")
        except Exception as e:
            print(f"Metrics error: {e}")
            
        self.after(2000, self.update_metrics_loop)

    def append_chat(self, sender, message):
        self.chat_display.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        prefix = f"[{timestamp}] "
        if sender == "USER":
            color_msg = f"{prefix}>>> {message}\n\n"
        elif sender == "GHOSTKEY":
            color_msg = f"{prefix}GHOSTKEY: {message}\n\n"
        else:
            color_msg = f"{prefix}[{sender}] {message}\n\n"
            
        self.chat_display.insert("end", color_msg)
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def send_message(self):
        msg = self.input_entry.get()
        if not msg.strip(): return
        
        self.input_entry.delete(0, "end")
        self.append_chat("USER", msg)
        
        # Run AI think in the background thread
        asyncio.run_coroutine_threadsafe(self.ai_think(msg), self.loop)

    async def ai_think(self, query):
        try:
            # Quadbrain handles tool selection, reasoning, etc.
            result = await self.master_ai.think(query, character_id=self.current_persona)
            answer = result.get("answer", "Protocol error: No response.")
            self.after(0, lambda: self.append_chat(self.current_persona.upper(), answer))
        except Exception as e:
            self.after(0, lambda: self.append_chat("ERROR", str(e)))

def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == "__main__":
    # Create background loop for Async tasks (like AI thinking)
    ai_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_async_loop, args=(ai_loop,), daemon=True)
    t.start()

    # Create and run UI
    app = GhostkeyDesktopApp(ai_loop)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.destroy()
