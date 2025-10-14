import { ChatInterface } from "@/components/ChatInterface";
import kuBackground from "@/assets/ku-background.jpg";

const Index = () => {
  return (
    <div 
      className="flex flex-col min-h-screen bg-gradient-subtle relative overflow-hidden"
      style={{
        backgroundImage: `url(${kuBackground})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundAttachment: 'fixed'
      }}
    >
      <div className="absolute inset-0 bg-background/85 backdrop-blur-sm" />
      
      <header className="relative py-3 border-b border-border/50 bg-background/60 backdrop-blur-md shadow-sm">
        <div className="max-w-4xl mx-auto px-4 w-full">
          <div className="flex items-center w-full">
            <div className="w-1/3" />

            <div className="w-1/3 text-center">
              <h1 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-primary via-primary-glow to-primary bg-clip-text text-transparent">
                KU-Talk
              </h1>
              <p className="text-center text-xs text-muted-foreground mt-0.5">건국대학교 AI 챗봇</p>
            </div>

            <div className="w-1/3 text-right text-sm font-semibold text-muted-foreground">
              AI융합연구센터
            </div>
          </div>
        </div>
      </header>
      
      <main className="relative flex-1 flex flex-col pt-[8vh] pb-0 min-h-0">
        <div className="flex-1 flex items-stretch w-full px-[10%] min-h-0">
          <div className="w-full">
            <ChatInterface />
          </div>
        </div>
      </main>
    </div>
  );
};

export default Index;
